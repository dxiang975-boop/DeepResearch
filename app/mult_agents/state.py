"""状态定义模块：声明多智能体工作流共享的 ResearchState 结构。

ResearchState 可以理解为整个 LangGraph 工作流的“共享工作台”：
每个节点都会从这里读取自己需要的数据，并把自己的处理结果写回这里。
后续节点再基于这些字段继续搜索、审查、分析或生成最终报告。
"""

import operator
from typing import Annotated, List
from typing_extensions import TypedDict
from langchain_core.messages import BaseMessage


class ResearchState(TypedDict):
    # 用户原始问题，也是整个研究任务的核心输入。
    query: str

    # 当前用户 ID，用于记忆系统、会话隔离和个性化上下文读取。
    user_id: str

    # 当前租户 ID，用于多租户场景下区分不同组织或业务空间的数据。
    tenant_id: str

    # 记忆系统拼接出来的历史上下文，会被注入到部分 Agent 的 prompt 中。
    memory_context: str

    # LangChain 消息列表。Annotated + operator.add 表示多个节点返回 messages 时会自动追加合并。
    messages: Annotated[List[BaseMessage], operator.add]

    # intent 节点的意图判断结果，通常是 direct 或 multiagent。
    intent: str

    # 当前工作流阶段标记，例如 initialized、planning completed 等，主要用于日志和前端展示。
    phase: str

    # planner 节点生成的总体研究目标或规划摘要。
    plan: str

    # planner 节点生成的报告大纲，每个 dict 通常表示一个章节或研究部分。
    outline: list[dict]

    # planner 节点拆解出的子问题，用于指导搜索、证据审查和最终报告结构。
    sub_questions: list[str]

    # 需要检索验证的研究问题列表，和 sub_questions 类似，但更偏向检索任务。
    research_questions: list[str]

    # 具体检索计划，每个 dict 通常包含 section_id、query、source_preference、reason 等字段。
    search_plan: list[dict]

    # 研究预算配置，例如最大轮数、最大来源数、最大 token 或最大耗时等。
    budget: dict

    # web_search 节点对网页搜索结果的摘要说明。
    web_search: str

    # local_rag 节点对本地知识库检索结果的摘要说明。
    local_rag: str

    # web_search 节点筛选出的网页证据列表，来源于 Bocha Web Search。
    web_evidence: list[dict]

    # local_rag 节点筛选出的本地知识库证据列表，来源于 Milvus/RAG。
    local_evidence: list[dict]

    # deep_dive 节点合并、去重、打分后的统一证据池，后续 analyze 和 write 主要依赖它。
    evidence_pool: list[dict]

    # deep_dive 节点输出的证据审查摘要。
    deep_dive: str

    # 证据审查结果摘要，通常和 deep_dive 字段内容接近，用于兼容或展示。
    audit: str

    # 证据审查标记，例如低可信度、证据冲突、缺少证据等风险提示。
    audit_flags: list[dict]

    # analyze 节点生成的分析总结。
    analysis: str

    # analyze 节点判断是否还需要继续补充搜索；为 True 时会进入 reflect 节点。
    needs_more_research: bool

    # analyze 节点发现的信息缺口，用于 reflect 节点生成补搜问题。
    missing_gaps: list[str]

    # reflect 节点生成的补充检索计划，下一轮 web_search/local_rag 会优先使用它。
    supplementary_queries: list[dict]

    # analyze 节点形成的核心发现或结论，每条 finding 通常会绑定 source_ids。
    findings: list[dict]

    # 结论与证据来源的映射关系，用于说明每个 claim 由哪些 source_id 支撑。
    claim_map: list[dict]

    # deep_dive 节点生成的来源索引，write 节点只能引用这里存在的合法 source_id。
    source_index: list[dict]

    # 网页检索统计信息，例如查询数、原始结果数、保留数、丢弃数等。
    web_retrieval_stats: dict

    # 本地 RAG 检索统计信息，例如查询数、原始结果数、保留数、丢弃数等。
    local_retrieval_stats: dict

    # 网页搜索轨迹，记录每次 query、原始结果、保留/拒绝结果和原因，便于调试和报告附录展示。
    web_search_trace: list[dict]

    # 本地知识库检索轨迹，记录每次本地检索 query、结果和筛选过程。
    local_rag_trace: list[dict]

    # 代码生成相关字段，当前主工作流基本未使用，属于预留/旧流程字段。
    code: str

    # 当前草稿内容，节点中间结果或 writer 生成的报告初稿会写入这里。
    draft: str

    # 最终输出内容。direct_answer 或 write 节点完成后，后端主要读取这个字段返回给前端。
    final: str

    # 当前研究迭代轮次。reflect 每触发一轮补搜，一般会将它加 1。
    iteration: int

    # 最大研究迭代轮次。analyze 后如果 iteration 达到该值，会强制进入 write，避免无限循环。
    max_iterations: int


def create_initial_state(
    query: str,
    max_iterations: int,
    user_id: str,
    tenant_id: str,
    memory_context: str = "",
) -> ResearchState:
    return {
        "query": query,
        "user_id": user_id,
        "tenant_id": tenant_id,
        "memory_context": memory_context,
        "messages": [],
        "intent": "",
        "phase": "initialized",
        "plan": "",
        "outline": [],
        "sub_questions": [],
        "research_questions": [],
        "search_plan": [],
        "budget": {},
        "web_search": "",
        "local_rag": "",
        "web_evidence": [],
        "local_evidence": [],
        "evidence_pool": [],
        "deep_dive": "",
        "audit": "",
        "audit_flags": [],
        "analysis": "",
        "needs_more_research": False,
        "missing_gaps": [],
        "supplementary_queries": [],
        "findings": [],
        "claim_map": [],
        "source_index": [],
        "web_retrieval_stats": {},
        "local_retrieval_stats": {},
        "web_search_trace": [],
        "local_rag_trace": [],
        "code": "",
        "draft": "",
        "final": "",
        "iteration": 0,
        "max_iterations": max_iterations,
    }
