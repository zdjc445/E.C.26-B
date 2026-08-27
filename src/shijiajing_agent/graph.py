"""主图装配（方案 §9.1）。节点全部由依赖注入创建，端口由 adapters/ 提供。"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, cast

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command
from pydantic import BaseModel

from shijiajing_agent.nodes.hitl_nodes import (
    make_clarification_interrupt_node,
    make_memory_confirmation_interrupt_node,
    make_recognition_review_interrupt_node,
    make_same_item_review_interrupt_node,
)
from shijiajing_agent.nodes.input_nodes import (
    load_session_node,
    prepare_subject_node,
    validate_input_node,
)
from shijiajing_agent.nodes.intent_nodes import (
    make_apply_memory_node,
    make_merge_constraints_node,
    make_parse_intent_node,
    make_validate_constraints_node,
)
from shijiajing_agent.nodes.matching_nodes import make_match_same_item_node, make_split_sku_node
from shijiajing_agent.nodes.memory_nodes import (
    append_turn_summary_node,
    make_commit_memory_node,
    make_prepare_memory_mutations_node,
)
from shijiajing_agent.nodes.ranking_nodes import make_rank_groups_node
from shijiajing_agent.nodes.response_nodes import (
    make_build_clarification_node,
    make_build_failed_node,
    make_build_no_results_node,
    make_build_response_node,
)
from shijiajing_agent.ports.dependencies import AgentGraphDependenciesPort
from shijiajing_agent.routing import route_after_validation
from shijiajing_agent.state import AgentState, NativeTurnInput
from shijiajing_agent.subgraphs.explanation import build_explanation_subgraph
from shijiajing_agent.subgraphs.intent import build_intent_subgraph
from shijiajing_agent.subgraphs.memory import build_memory_subgraph
from shijiajing_agent.subgraphs.outputs import (
    ExplanationSubgraphOutput,
    IntentSubgraphOutput,
    MemorySubgraphOutput,
    RecognitionSubgraphOutput,
    RetrievalSubgraphOutput,
)
from shijiajing_agent.subgraphs.recognition import build_recognition_subgraph
from shijiajing_agent.subgraphs.retrieval import build_retrieval_subgraph


def _route_after_clarification(state: AgentState) -> str:
    return (
        "parse_intent_resume"
        if state.get("next_action") == "clarification_resumed"
        else "build_response"
    )


def _route_after_retrieval_subgraph(state: AgentState) -> str:
    """把检索子图的 terminal state 接回根图的响应/匹配分支。"""
    if state.get("next_action") == "failed":
        return "build_failed_response"
    if state.get("candidates"):
        return "match_same_item"
    return "build_no_results"


def _make_subgraph_node(
    subgraph: CompiledStateGraph[AgentState, None, AgentState, AgentState],
    output_model: type[BaseModel],
    *,
    node_name: str,
) -> Callable[[AgentState], Awaitable[dict[str, Any]]]:
    """把 compiled subgraph 的完整快照收敛为根图授权字段。

    LangGraph 子图 invocation 会返回其完整 state；识别和意图又在根图中并行，
    直接把完整结果回写会让诸如 ``schema_version`` 等只读字段发生并发写入。
    这个边界适配器只向根图传播方案授权的字段，同时保留 append-only 事件字段。
    """

    append_only_fields = {"notices", "errors", "fallbacks", "node_events"}

    async def invoke(state: AgentState) -> dict[str, Any]:
        try:
            # 当前 LangGraph stub 的 ainvoke overload含未参数化 Command；在已读取的
            # v1 values 边界收窄为状态映射，避免该未知类型进入根图。
            invoke = cast(
                Callable[..., Awaitable[dict[str, Any]]],
                subgraph.ainvoke,  # pyright: ignore[reportUnknownMemberType]
            )
            result = cast(AgentState, await invoke(state))
            payload: dict[str, Any] = {
                field: result[field] for field in output_model.model_fields if field in result
            }
            validated = output_model.model_validate(payload)
            # 保留 RecognitionResult、IntentPatch、RetrievalQuery 等领域对象；
            # model_dump() 会把它们递归转换成 dict，破坏根图节点的类型契约。
            delta = {field: getattr(validated, field) for field in validated.model_fields_set}
            for field in append_only_fields:
                if not delta.get(field):
                    delta.pop(field, None)
            return delta
        except Exception as exc:
            try:
                attribute_name = "node_name"
                setattr(exc, attribute_name, node_name)
            except Exception:
                pass
            raise

    return invoke


def join_understanding_node(state: AgentState) -> dict[str, Any]:
    """Recognition/Intent 汇合点；两分支只在此之后进入 Memory/约束合并。"""
    del state
    return {"next_action": "understanding_joined"}


def _understanding_marker(state: AgentState) -> dict[str, Any]:
    del state
    return {}


def stream_values(
    graph: CompiledStateGraph[AgentState, None, NativeTurnInput, AgentState],
    input_state: NativeTurnInput | Command[str],
    config: RunnableConfig | None,
) -> AsyncIterator[AgentState]:
    """把 LangGraph v1 values stream 收敛为项目状态流。"""
    stream = cast(
        Callable[..., AsyncIterator[AgentState]],
        graph.astream,  # pyright: ignore[reportUnknownMemberType]
    )
    return stream(input_state, config, stream_mode="values")


def build_graph(
    deps: AgentGraphDependenciesPort,
) -> CompiledStateGraph[AgentState, None, NativeTurnInput, AgentState]:
    """按 §9.1 主图装配。deps 需包含 taxonomy、settings 与全部端口。"""
    # LangGraph builder 的 overloaded stub 在当前版本将 CachePolicy 的类型参数暴露为
    # Unknown；只在 builder 装配点保留 Any，compiled graph 立即恢复项目状态类型。
    g: Any = StateGraph(AgentState, input_schema=NativeTurnInput)

    g.add_node("validate_input", validate_input_node)
    g.add_node("load_session", load_session_node)
    g.add_node("prepare_subject", prepare_subject_node)
    g.add_node("recognition_start", _understanding_marker)
    g.add_node("intent_start", _understanding_marker)
    g.add_node("recognition_done", _understanding_marker)
    g.add_node("intent_done", _understanding_marker)
    g.add_node("join_understanding", join_understanding_node)
    g.add_node("parse_intent_resume", make_parse_intent_node(deps))
    g.add_node("merge_constraints", make_merge_constraints_node(deps))
    g.add_node("validate_constraints", make_validate_constraints_node(deps))
    g.add_node("build_clarification", make_build_clarification_node(deps))
    g.add_node("match_same_item", make_match_same_item_node(deps))
    g.add_node("split_sku", make_split_sku_node(deps))
    g.add_node("rank_groups", make_rank_groups_node(deps))
    g.add_node("build_response", make_build_response_node(deps))
    g.add_node("build_no_results", make_build_no_results_node(deps))
    g.add_node("build_failed_response", make_build_failed_node(deps))

    # 专业子图由根图统一装配；子图只写各自授权的 AgentState 字段。
    g.add_node(
        "recognition_subgraph",
        _make_subgraph_node(
            build_recognition_subgraph(deps),
            RecognitionSubgraphOutput,
            node_name="recognition_subgraph",
        ),
    )
    g.add_node(
        "intent_subgraph",
        _make_subgraph_node(
            build_intent_subgraph(deps),
            IntentSubgraphOutput,
            node_name="intent_subgraph",
        ),
    )
    g.add_node(
        "retrieval_subgraph",
        _make_subgraph_node(
            build_retrieval_subgraph(deps),
            RetrievalSubgraphOutput,
            node_name="retrieval_subgraph",
        ),
    )
    g.add_node(
        "explanation_subgraph",
        _make_subgraph_node(
            build_explanation_subgraph(deps),
            ExplanationSubgraphOutput,
            node_name="explanation_subgraph",
        ),
    )

    memory_enabled = bool(getattr(getattr(deps, "settings", None), "memory_enabled", False))
    memory_recall_enabled = bool(
        getattr(getattr(deps, "settings", None), "memory_recall_enabled", True)
    )
    memory_commit_enabled = bool(
        getattr(getattr(deps, "settings", None), "memory_commit_enabled", True)
    )
    memory_runtime_enabled = memory_enabled and memory_recall_enabled
    hitl_enabled = bool(getattr(getattr(deps, "settings", None), "hitl_enabled", False))

    def append_summary(state: AgentState) -> dict[str, Any]:
        return append_turn_summary_node(
            state,
            recent_turns_limit=deps.settings.recent_turns_limit,
            recent_turns_max_bytes=deps.settings.recent_turns_max_bytes,
        )

    # recent_turns 是 bounded conversation memory，与长期 Memory 的开关独立。
    g.add_node("append_turn_summary", append_summary)
    if memory_runtime_enabled and getattr(deps, "memory", None) is not None:
        g.add_node(
            "memory_subgraph",
            _make_subgraph_node(
                build_memory_subgraph(deps, include_commit=False, include_prepare=False),
                MemorySubgraphOutput,
                node_name="memory_subgraph",
            ),
        )
        g.add_node("apply_memory", make_apply_memory_node(deps))
        if memory_commit_enabled:
            g.add_node("prepare_memory_mutations", make_prepare_memory_mutations_node(deps))
            g.add_node("commit_memory", make_commit_memory_node(deps))
    if hitl_enabled:
        g.add_node("clarification_interrupt", make_clarification_interrupt_node(deps))
        g.add_node("recognition_review_interrupt", make_recognition_review_interrupt_node(deps))
        g.add_node("same_item_review_interrupt", make_same_item_review_interrupt_node(deps))
        if (
            memory_runtime_enabled
            and getattr(deps, "memory", None) is not None
            and memory_commit_enabled
            and deps.settings.memory_confirmation_required
        ):
            g.add_node(
                "memory_confirmation_interrupt", make_memory_confirmation_interrupt_node(deps)
            )

    g.add_edge(START, "validate_input")
    g.add_edge("validate_input", "load_session")
    g.add_edge("load_session", "prepare_subject")

    g.add_edge("prepare_subject", "recognition_start")
    g.add_edge("prepare_subject", "intent_start")
    g.add_edge("recognition_start", "recognition_subgraph")
    if hitl_enabled:
        g.add_edge("recognition_subgraph", "recognition_review_interrupt")
        g.add_edge("recognition_review_interrupt", "recognition_done")
    else:
        g.add_edge("recognition_subgraph", "recognition_done")
    g.add_edge("intent_start", "intent_subgraph")
    g.add_edge("intent_subgraph", "intent_done")
    g.add_edge(["recognition_done", "intent_done"], "join_understanding")
    if memory_runtime_enabled and getattr(deps, "memory", None) is not None:
        # 先合并本轮显式意图得到 current category，再构造 MemoryQuery。
        g.add_edge("join_understanding", "merge_constraints")
        g.add_edge("merge_constraints", "memory_subgraph")
        g.add_edge("memory_subgraph", "apply_memory")
        g.add_edge("apply_memory", "validate_constraints")
    else:
        g.add_edge("join_understanding", "merge_constraints")
        g.add_edge("merge_constraints", "validate_constraints")

    g.add_conditional_edges(
        "validate_constraints",
        route_after_validation,
        {
            "build_clarification": "build_clarification",
            "rewrite_query": "retrieval_subgraph",
        },
    )
    if hitl_enabled:
        g.add_edge("build_clarification", "clarification_interrupt")
        g.add_conditional_edges(
            "clarification_interrupt",
            _route_after_clarification,
            {
                "parse_intent_resume": "parse_intent_resume",
                "build_response": "build_response",
            },
        )
    else:
        g.add_edge("build_clarification", "build_response")
    g.add_edge("parse_intent_resume", "merge_constraints")
    g.add_conditional_edges(
        "retrieval_subgraph",
        _route_after_retrieval_subgraph,
        {
            "build_no_results": "build_no_results",
            "build_failed_response": "build_failed_response",
            "match_same_item": "match_same_item",
        },
    )
    if hitl_enabled:
        g.add_edge("match_same_item", "same_item_review_interrupt")
        g.add_edge("same_item_review_interrupt", "split_sku")
    else:
        g.add_edge("match_same_item", "split_sku")
    g.add_edge("split_sku", "rank_groups")
    g.add_edge("rank_groups", "explanation_subgraph")
    g.add_edge("explanation_subgraph", "build_response")

    g.add_edge("build_no_results", "build_response")

    if (
        memory_runtime_enabled
        and memory_commit_enabled
        and getattr(deps, "memory", None) is not None
    ):
        # 业务响应先构建完成，再准备/确认/提交长期记忆。
        g.add_edge("build_response", "prepare_memory_mutations")
        g.add_edge("build_failed_response", "prepare_memory_mutations")
        if hitl_enabled and deps.settings.memory_confirmation_required:
            g.add_edge("prepare_memory_mutations", "memory_confirmation_interrupt")
            g.add_edge("memory_confirmation_interrupt", "commit_memory")
        else:
            g.add_edge("prepare_memory_mutations", "commit_memory")
        g.add_edge("commit_memory", "append_turn_summary")
        g.add_edge("append_turn_summary", END)
    else:
        # 失败也是已完成的 terminal response，需要进入 bounded conversation memory。
        g.add_edge("build_failed_response", "append_turn_summary")
        g.add_edge("build_response", "append_turn_summary")
        g.add_edge("append_turn_summary", END)
    if deps.graph_checkpointer is None:
        return cast(
            CompiledStateGraph[AgentState, None, NativeTurnInput, AgentState],
            g.compile(name="shijiajing-supervisor"),
        )
    return cast(
        CompiledStateGraph[AgentState, None, NativeTurnInput, AgentState],
        g.compile(checkpointer=deps.graph_checkpointer, name="shijiajing-supervisor"),
    )
