
import logging

from langgraph.graph import END, START, StateGraph

from .nodes import (
    analyze_node,
    bind_agent,
    deep_dive_node,
    direct_answer_node,
    intent_node,
    local_rag_node,
    plan_node,
    reflect_node,
    web_search_node,
    write_node,
)
from .state import ResearchState


logger = logging.getLogger("mult_agents")


def route_after_intent(state: ResearchState) -> str:
    """intent 节点执行后的条件路由函数。

    intent_node 会把识别结果写入 state["intent"]：
    - "direct"：说明是闲聊、简单问答，直接进入 direct_answer。
    - "multiagent" 或其他值：说明需要深度研究，进入 plan。

    LangGraph 会根据这个函数返回的字符串，在 add_conditional_edges
    配置的映射表里找到下一个节点。
    """
    if state.get("intent") == "direct":
        return "direct_answer"
    return "plan"


def should_continue_research(state: ResearchState) -> str:
    """analyze 节点执行后的条件路由函数。

    Analyst 会判断当前证据是否足够回答问题，并写入：
    - state["needs_more_research"]：是否需要补充检索。
    - state["missing_gaps"]：还缺哪些信息。

    如果证据不足，并且还没超过最大迭代次数，就进入 reflect 节点生成补搜计划。
    否则进入 write 节点撰写最终报告。
    """
    iteration = state.get("iteration", 0)
    max_iter = state.get("max_iterations", 2)

    # 已达到最大迭代次数时，不再补搜，直接写最终报告。
    if iteration >= max_iter:
        return "write"

    # Analyst 判断证据不足时，进入 reflect 节点生成补搜 query。
    if state.get("needs_more_research", False):
        return "reflect"

    # 证据已经够用，进入 Writer。
    return "write"


def build_app(agents, checkpointer):
    """构建并编译 LangGraph 工作流。

    参数说明：
    - agents：AgentBundle，里面包含 intent_router、planner、scout_web 等 Agent。
    - checkpointer：LangGraph 的状态保存器，可用内存、Postgres、Redis 等后端。

    返回值：
    - 编译后的 LangGraph app，外部可以调用 app.invoke(...) 或 app.stream(...)。
    """
    # StateGraph 表示这个工作流的共享状态类型是 ResearchState。
    # 每个节点接收 ResearchState，并返回部分字段更新。
    workflow = StateGraph(ResearchState)

    # 注册节点：节点名 -> 可执行函数。
    # bind_agent 的作用是把“节点函数”和“对应 Agent 实例”绑定起来。
    # 例如 intent_node 本身需要 agent 参数，bind_agent 后 LangGraph 只需要传 state。
    workflow.add_node("intent", bind_agent(intent_node, agents.intent_router, "intent_router"))
    workflow.add_node("direct_answer", bind_agent(direct_answer_node, agents.direct_responder, "direct_responder"))
    workflow.add_node("plan", bind_agent(plan_node, agents.planner, "planner"))
    workflow.add_node("web_search", bind_agent(web_search_node, agents.scout_web, "scout_web"))
    workflow.add_node("local_rag", bind_agent(local_rag_node, agents.scout_local, "scout_local"))
    workflow.add_node("deep_dive", bind_agent(deep_dive_node, agents.evidence_judge, "evidence_judge"))
    workflow.add_node("analyze", bind_agent(analyze_node, agents.analyst, "analyst"))

    # reflect 复用 planner Agent，不单独创建一个新模型角色。
    # 它的节点函数 reflect_node 会给 planner 一个“根据缺口生成补搜计划”的 prompt。
    workflow.add_node("reflect", bind_agent(reflect_node, agents.planner, "planner"))
    workflow.add_node("write", bind_agent(write_node, agents.writer, "writer"))

    # 入口边：所有请求都先进入 intent 节点做意图识别。
    workflow.add_edge(START, "intent")

    # intent 后的分流：
    # - direct_answer：简单问题，直接回答，避免不必要的检索和 token 消耗。
    # - plan：复杂研究问题，进入多 Agent 深度研究链路。
    workflow.add_conditional_edges(
        "intent",
        route_after_intent,
        {
            "direct_answer": "direct_answer",
            "plan": "plan",
        },
    )

    # Planner 完成问题拆解后，同时触发两条检索链路：
    # - web_search：调用网络搜索，拿外部实时信息。
    # - local_rag：查询本地向量知识库，拿内部/本地知识。
    #
    # 在 LangGraph 中，同一个节点连到多个下游节点时，下游节点会基于同一份状态继续执行。
    workflow.add_edge("plan", "web_search")
    workflow.add_edge("plan", "local_rag")

    # 两条检索链路完成后，都汇入 deep_dive。
    # deep_dive 负责把 web_evidence 和 local_evidence 合并、去重、评分、审计。
    workflow.add_edge("web_search", "deep_dive")
    workflow.add_edge("local_rag", "deep_dive")

    # 证据审计完成后，进入 Analyst 做结论归纳和完备性判断。
    workflow.add_edge("deep_dive", "analyze")

    # analyze 后再次做条件判断：
    # - 如果证据不足且没超过迭代次数，进入 reflect。
    # - 如果证据足够或已到上限，进入 write。
    workflow.add_conditional_edges(
        "analyze",
        should_continue_research,
        {
            "reflect": "reflect",
            "write": "write",
        },
    )

    # Reflect 生成 supplementary_queries 后，回到两条检索链路继续补搜。
    # 这形成了“分析 -> 发现缺口 -> 补搜 -> 再分析”的闭环。
    workflow.add_edge("reflect", "web_search")
    workflow.add_edge("reflect", "local_rag")

    # 终止边：
    # - direct_answer 直接结束。
    # - write 生成最终报告后结束。
    workflow.add_edge("direct_answer", END)
    workflow.add_edge("write", END)

    # compile 会把上面定义的节点、边、条件路由编译成可执行应用。
    # checkpointer 用于保存/恢复图状态，例如支持多轮 thread_id 会话。
    return workflow.compile(checkpointer=checkpointer)
