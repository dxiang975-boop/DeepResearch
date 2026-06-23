import asyncio
from threading import Lock, Thread
from typing import AsyncIterator, Callable

from mult_agents.config import AppConfig
from mult_agents.graph import build_app as build_workflow_app
from mult_agents.main import build_agents, build_checkpointer, build_memory_manager
from mult_agents.state import create_initial_state


"""
class WorkflowService
    │
    ├── __init__(config_path)
    │   └── 初始化服务对象，保存配置路径，准备锁、基础配置、记忆管理器和 LangGraph app。
    │
    ├── _ensure_initialized()
    │   └── 懒加载初始化：读取配置，构建 MemoryManager、Agent、checkpointer 和 LangGraph 工作流。
    │
    ├── _build_runtime_config(...)
    │   └── 根据本次请求的 user_id、thread_id、tenant_id 等参数，生成请求级运行配置。
    │
    ├── _run_sync(...)
    │   └── 非流式执行入口：创建初始 ResearchState，调用 LangGraph invoke，返回最终答案。
    │
    ├── _node_message(node_name)
    │   └── 把 LangGraph 节点名转换成前端展示用的中文阶段提示。
    │
    ├── _run_sync_with_events(..., emit)
    │   └── 流式执行核心：调用 LangGraph stream，每个节点完成时通过 emit 发出阶段事件。
    │
    ├── async run(...)
    │   └── 给 /run 接口使用，把同步的 _run_sync 放到线程池执行，只返回 final。
    │
    ├── async run_with_route(...)
    │   └── 和 run 类似，但额外返回 route，用于知道本次走 direct 还是 multiagent。
    │
    └── async stream_events(...)
        │
        ├── emit(event)
        │   └── 内部嵌套函数：把后台线程里的事件安全放入 asyncio.Queue。
        │
        └── worker()
            └── 内部嵌套函数：在线程中执行 _run_sync_with_events，并发送 route/final/error/done 事件。
"""


# WorkflowService 是后端 API 和 LangGraph 多 Agent 工作流之间的连接层。
# router 只负责接收 HTTP 请求，真正的配置加载、Agent 初始化、状态创建、
# 工作流调用、记忆读写、SSE 事件转换都集中在这个类里。
class WorkflowService:
    def __init__(self, config_path: str):
        # config_path 通常指向项目根目录下的 config.json。
        self._config_path = config_path

        # FastAPI 可能同时收到多个请求，Lock 用来保证工作流只初始化一次。
        self._lock = Lock()
        self._initialized = False

        # _base_config 保存从 config.json/.env 合并出来的基础配置。
        # 每次请求可以覆盖 user_id、thread_id、tenant_id 等运行时字段。
        self._base_config: AppConfig | None = None

        # _memory_manager 负责短期记忆、长期记忆、语义记忆的统一读写。
        # 如果 ENABLE_MEMORY=false 或初始化失败，它可能是 None。
        self._memory_manager = None

        # _app 是编译后的 LangGraph 应用，也就是整个多 Agent 工作流。
        self._app = None


    # 把 Agent 系统搭起来
    def _ensure_initialized(self) -> None:
        # 懒加载初始化：第一次真正调用工作流时才构建模型、Agent、Graph。
        # 这样 FastAPI 启动更快，也避免应用导入阶段就连接外部服务。
        if self._initialized:
            return

        # 双重检查锁：多个请求并发进来时，只有第一个请求执行初始化。
        with self._lock:
            if self._initialized:
                return

            # 1. 读取基础配置。
            base_config = AppConfig.from_file(self._config_path)

            # 2. 根据配置初始化记忆系统。
            self._memory_manager = build_memory_manager(base_config)

            # 3. 创建各个 Agent：IntentRouter、Planner、WebScout、Writer 等。
            agents = build_agents(base_config.model, base_config.api_key, base_config)

            # 4. 创建 LangGraph checkpointer，用于保存图执行状态。
            checkpointer = build_checkpointer(base_config)

            # 5. 把 Agent 绑定到 LangGraph 节点上，得到可执行工作流。
            self._app = build_workflow_app(agents, checkpointer)
            self._base_config = base_config
            self._initialized = True

    def _build_runtime_config(
        self,
        user_id: str,
        thread_id: str,
        tenant_id: str,
        max_iterations: int | None,
        enable_memory: bool | None,
    ) -> AppConfig:
        # 每次请求都有自己的 user/thread/tenant/max_iterations。
        # 这里不是修改全局配置，而是基于 _base_config 生成一份请求级配置。
        if self._base_config is None:
            raise RuntimeError("service not initialized")

        overrides = {
            "user_id": user_id,
            "thread_id": thread_id,
            "tenant_id": tenant_id,
            "max_iterations": max_iterations if max_iterations is not None else self._base_config.max_iterations,
        }
        if enable_memory is not None:
            overrides["enable_memory"] = enable_memory

        return self._base_config.with_overrides(**overrides)

    def _run_sync(
        self,
        query: str,
        user_id: str,
        thread_id: str,
        tenant_id: str,
        max_iterations: int | None,
        enable_memory: bool | None,
    ) -> tuple[str, str]:
        # 非流式执行版本：对应 /api/v1/research/run。
        # 它会等待 LangGraph 完整执行结束，然后一次性返回最终答案。
        self._ensure_initialized()
        runtime_config = self._build_runtime_config(
            user_id=user_id,
            thread_id=thread_id,
            tenant_id=tenant_id,
            max_iterations=max_iterations,
            enable_memory=enable_memory,
        )

        # 执行前先读取相关记忆，拼成 memory_context 注入初始状态。
        memory_context = ""
        if self._memory_manager and runtime_config.enable_memory:
            memory_context = self._memory_manager.build_personalized_prompt_context(
                user_id=runtime_config.user_id,
                thread_id=runtime_config.thread_id,
                query=query,
                tenant_id=runtime_config.tenant_id,
                max_memories=runtime_config.memory_top_k,
            )

        # create_initial_state 会创建 ResearchState。
        # 后续所有 LangGraph 节点都基于这个共享状态读写数据。
        state = create_initial_state(
            query=query,
            max_iterations=runtime_config.max_iterations,
            user_id=runtime_config.user_id,
            tenant_id=runtime_config.tenant_id,
            memory_context=memory_context,
        )

        # invoke 是 LangGraph 的一次性调用方式：输入初始 state，输出最终 state。
        # configurable.thread_id 给 checkpointer 用，用来区分不同会话线程。
        result = self._app.invoke(
            state,
            {"configurable": {"thread_id": runtime_config.thread_id}},
        )
        final = result.get("final", "")
        route = str(result.get("intent", "multiagent"))

        # 执行结束后，把本轮 query/final 保存进记忆系统，供后续轮次检索。
        if self._memory_manager and runtime_config.enable_memory:
            self._memory_manager.persist_turn(
                tenant_id=runtime_config.tenant_id,
                user_id=runtime_config.user_id,
                thread_id=runtime_config.thread_id,
                query=query,
                answer=final,
            )

        return final, route

    @staticmethod
    def _node_message(node_name: str) -> str:
        # 把 LangGraph 的节点名转换成前端可展示的阶段文案。
        mapping = {
            "intent": "Intent Router 正在识别问题意图",
            "direct_answer": "Direct Responder 正在快速作答",
            "plan": "Planner 正在拆解问题",
            "web_search": "Web Scout 正在检索网络证据",
            "local_rag": "Local Scout 正在检索本地知识库",
            "deep_dive": "Evidence Judge 正在进行证据裁判",
            "analyze": "Analyst 正在生成结论",
            "reflect": "Reflect 正在生成补搜计划",
            "write": "Writer 正在撰写最终报告",
        }
        return mapping.get(node_name, f"{node_name} 正在执行")

    def _run_sync_with_events(
        self,
        query: str,
        user_id: str,
        thread_id: str,
        tenant_id: str,
        max_iterations: int | None,
        enable_memory: bool | None,
        emit: Callable[[dict], None],
    ) -> tuple[str, str]:
        # 流式执行版本：对应 /api/v1/research/stream。
        # 和 _run_sync 的核心区别是：它会在每个 LangGraph 节点完成时 emit 阶段事件。
        self._ensure_initialized()
        runtime_config = self._build_runtime_config(
            user_id=user_id,
            thread_id=thread_id,
            tenant_id=tenant_id,
            max_iterations=max_iterations,
            enable_memory=enable_memory,
        )

        memory_context = ""
        if self._memory_manager and runtime_config.enable_memory:
            memory_context = self._memory_manager.build_personalized_prompt_context(
                user_id=runtime_config.user_id,
                thread_id=runtime_config.thread_id,
                query=query,
                tenant_id=runtime_config.tenant_id,
                max_memories=runtime_config.memory_top_k,
            )

        state = create_initial_state(
            query=query,
            max_iterations=runtime_config.max_iterations,
            user_id=runtime_config.user_id,
            tenant_id=runtime_config.tenant_id,
            memory_context=memory_context,
        )

        final = ""
        route = "multiagent"
        config = {"configurable": {"thread_id": runtime_config.thread_id}}

        # stream(..., stream_mode="updates") 会逐步返回每个节点更新了哪些字段。
        # update 的形态通常类似：{"plan": {...}} 或 {"web_search": {...}}。
        for update in self._app.stream(state, config, stream_mode="updates"):
            if not isinstance(update, dict):
                continue

            for node_name, node_output in update.items():
                emit({"type": "phase", "node": node_name, "message": self._node_message(str(node_name))})

                if isinstance(node_output, dict):
                    # intent 节点会决定本次请求走 direct 还是 multiagent。
                    if node_name == "intent":
                        detected = str(node_output.get("intent", route)).strip().lower()
                        if detected in {"direct", "multiagent"}:
                            route = detected

                    # direct_answer 或 write 节点通常会产生 final。
                    value = node_output.get("final")
                    if value:
                        final = str(value)

        # 兜底逻辑：如果 stream 没拿到 final，就再用 invoke 获取最终状态。
        # 正常情况下不应该频繁走到这里。
        if not final:
            result = self._app.invoke(state, config)
            final = str(result.get("final", ""))
            route = str(result.get("intent", route)).strip().lower()

        if self._memory_manager and runtime_config.enable_memory:
            self._memory_manager.persist_turn(
                tenant_id=runtime_config.tenant_id,
                user_id=runtime_config.user_id,
                thread_id=runtime_config.thread_id,
                query=query,
                answer=final,
            )

        return final, route

    async def run(
        self,
        query: str,
        user_id: str,
        thread_id: str,
        tenant_id: str,
        max_iterations: int | None,
        enable_memory: bool | None,
    ) -> str:
        # FastAPI 的路由函数是 async，但 LangGraph invoke 是同步阻塞调用。
        # asyncio.to_thread 把同步工作丢到线程池，避免阻塞事件循环。
        final, _ = await asyncio.to_thread(
            self._run_sync,
            query,
            user_id,
            thread_id,
            tenant_id,
            max_iterations,
            enable_memory,
        )
        return final

    async def run_with_route(
        self,
        query: str,
        user_id: str,
        thread_id: str,
        tenant_id: str,
        max_iterations: int | None,
        enable_memory: bool | None,
    ) -> tuple[str, str]:
        # 和 run 类似，但额外返回 route，方便调用方知道走的是 direct(直接回答) 还是 multiagent（使用多agent）。
        return await asyncio.to_thread(
            self._run_sync,
            query,
            user_id,
            thread_id,
            tenant_id,
            max_iterations,
            enable_memory,
        )

    async def stream_events(
        self,
        query: str,
        user_id: str,
        thread_id: str,
        tenant_id: str,
        max_iterations: int | None,
        enable_memory: bool | None,
    ) -> AsyncIterator[dict]:
        # FastAPI StreamingResponse 需要一个异步迭代器。
        # 但 LangGraph stream 是同步迭代器，所以这里用后台线程执行工作流，
        # 再用 asyncio.Queue 把线程里的事件安全地传回 async 世界。
        queue: asyncio.Queue[dict] = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def emit(event: dict) -> None:
            # worker 线程不能直接 await queue.put，所以用 run_coroutine_threadsafe。
            asyncio.run_coroutine_threadsafe(queue.put(event), loop)

        def worker() -> None:
            try:
                final, route = self._run_sync_with_events(
                    query=query,
                    user_id=user_id,
                    thread_id=thread_id,
                    tenant_id=tenant_id,
                    max_iterations=max_iterations,
                    enable_memory=enable_memory,
                    emit=emit,
                )

                emit({"type": "route", "message": "已走直接回答路径" if route == "direct" else "已走多智能体研究路径"})
                emit(
                    {
                        "type": "final",
                        "query": query,
                        "user_id": user_id,
                        "thread_id": thread_id,
                        "tenant_id": tenant_id,
                        "final": final,
                    }
                )
            except Exception as exc:
                # 把后端异常转换成 SSE error 事件，前端会展示请求失败信息。
                emit({"type": "error", "message": str(exc)})
            finally:
                # 内部结束信号，不会返回给前端，只用来让 async generator 退出循环。
                emit({"type": "__done__"})

        Thread(target=worker, daemon=True).start()

        while True:
            event = await queue.get()
            if event.get("type") == "__done__":
                break
            yield event
