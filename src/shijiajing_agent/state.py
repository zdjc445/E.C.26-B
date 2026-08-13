"""Agent 状态定义（方案 §7.3）。

LangGraph TypedDict 状态。大体积字段不得无限进入 Checkpoint：
候选商品只保存后续节点所需字段；模型原始响应存入受限 trace 存储，
Checkpoint 中保存摘要和内容哈希。
"""

from __future__ import annotations

from typing import Any, Required, TypedDict

from shijiajing_agent.contracts import (
    AgentRequest,
    AgentResponse,
    Clarification,
    CompletionReason,
    IntentPatch,
    NormalizedCandidate,
    RankedGroup,
    RecognitionResult,
    RetrievalCandidate,
    RetrievalQuery,
    ShoppingConstraints,
    SkuGroup,
)

# 当前 Checkpoint schema 版本（§17.1）；不兼容版本拒绝直接加载，须显式迁移
SCHEMA_VERSION = "1.0"

# 固定的 dirty_flags（§10）
DIRTY_FLAGS = (
    "recognition_dirty",
    "normalization_dirty",
    "intent_dirty",
    "query_dirty",
    "retrieval_dirty",
    "matching_dirty",
    "ranking_dirty",
    "explanation_dirty",
)


class NodeEventRecord(TypedDict, total=False):
    trace_id: str
    session_id: str
    request_id: str
    turn_id: str
    node_name: str
    status: str
    started_at: str
    duration_ms: float
    provider: str | None
    model: str | None
    input_hash: str | None
    output_hash: str | None
    retry_count: int
    fallback_used: bool
    candidate_count_in: int | None
    candidate_count_out: int | None
    error_code: str | None


class FallbackRecord(TypedDict, total=False):
    node_name: str
    reason: str
    fallback_provider: str


class ErrorRecord(TypedDict, total=False):
    node_name: str
    error_code: str
    message: str


class ConflictRecord(TypedDict, total=False):
    reason_code: str
    field: str
    message: str
    a_value: Any
    b_value: Any


class AgentState(TypedDict, total=False):
    """§7.3 状态字段分组。"""

    # 标识
    schema_version: str
    session_id: str
    request_id: str
    turn_id: str
    trace_id: str
    state_version: int
    # 输入（previous_state 只由 facade 注入，不进入持久化）
    current_request: Required[AgentRequest]
    previous_state: AgentState | None
    subject_id: str | None
    image_ref: Any
    selected_option_id: str | None
    # 识别
    recognition: RecognitionResult | None
    recognition_history: list[RecognitionResult]
    recognition_id: str | None
    # 意图
    intent_patch: IntentPatch | None
    effective_constraints: ShoppingConstraints | None
    conflicts: list[ConflictRecord]
    # 检索
    retrieval_query: RetrievalQuery | None
    candidates: list[RetrievalCandidate]
    retrieval_attempts: int
    retrieval_fallback_used: bool
    relaxation_attempted: bool
    relaxed_attributes: list[str]
    # 匹配
    normalized_candidates: list[NormalizedCandidate]
    spu_clusters: list[list[int]]
    sku_groups: list[SkuGroup]
    # 输出
    ranked_groups: list[RankedGroup]
    clarification: Clarification | None
    evidence_bundle: Any
    explanation_text: str | None
    explanation_verified: bool
    response: AgentResponse | None
    notices: list[str]
    keywords: list[str]
    # 控制
    dirty_flags: dict[str, bool]
    retry_counters: dict[str, int]
    next_action: str
    completion_reason: CompletionReason | None
    is_resumed: bool
    resumed_node: str | None
    step_count: int
    # 可观测性
    node_events: list[NodeEventRecord]
    fallbacks: list[FallbackRecord]
    errors: list[ErrorRecord]


def new_state(
    *,
    schema_version: str,
    session_id: str,
    request_id: str,
    turn_id: str,
    trace_id: str,
    current_request: AgentRequest,
    subject_id: str | None = None,
) -> AgentState:
    """创建新的 AgentState。"""
    return AgentState(
        schema_version=schema_version,
        session_id=session_id,
        request_id=request_id,
        turn_id=turn_id,
        trace_id=trace_id,
        state_version=0,
        current_request=current_request,
        previous_state=None,
        subject_id=subject_id,
        recognition=None,
        recognition_history=[],
        recognition_id=None,
        intent_patch=None,
        effective_constraints=None,
        conflicts=[],
        retrieval_query=None,
        candidates=[],
        retrieval_attempts=0,
        retrieval_fallback_used=False,
        relaxation_attempted=False,
        relaxed_attributes=[],
        normalized_candidates=[],
        spu_clusters=[],
        sku_groups=[],
        ranked_groups=[],
        clarification=None,
        evidence_bundle=None,
        explanation_text=None,
        explanation_verified=False,
        response=None,
        notices=[],
        keywords=[],
        dirty_flags={name: False for name in DIRTY_FLAGS},
        retry_counters={},
        next_action="",
        completion_reason=None,
        is_resumed=False,
        resumed_node=None,
        step_count=0,
        node_events=[],
        fallbacks=[],
        errors=[],
    )


def mark_dirty(state: AgentState, *flags: str) -> None:
    for f in flags:
        state.setdefault("dirty_flags", {})[f] = True


def clean_dirty(state: AgentState, *flags: str) -> None:
    for f in flags:
        state.setdefault("dirty_flags", {})[f] = False
