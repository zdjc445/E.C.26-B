"""Agent 状态定义（方案 §7.3）。

LangGraph TypedDict 状态。大体积字段不得无限进入 Checkpoint：
候选商品只保存后续节点所需字段；模型原始响应存入受限 trace 存储，
Checkpoint 中保存摘要和内容哈希。
"""

from __future__ import annotations

from typing import Annotated, Any, Required, TypedDict

from shijiajing_agent.contracts import (
    AgentEventRecord,
    AgentExecutionContext,
    AgentInterrupt,
    AgentRequest,
    AgentResponse,
    AgentResult,
    AgentResultV2,
    CanonicalUnderstanding,
    Clarification,
    CompletionReason,
    ConversationTurnSummary,
    ExecutionPlan,
    ImageRef,
    IntentPatch,
    MatchPair,
    MemoryMutation,
    MemoryRecord,
    NormalizedCandidate,
    RankedGroup,
    RecognitionResult,
    RetrievalCandidate,
    RetrievalQuery,
    ShoppingConstraints,
    SkuGroup,
    SupervisorBudgetUsage,
    TaskRecord,
)
from shijiajing_agent.domain.evidence import EvidenceBundle
from shijiajing_agent.errors import TaskResultConflictError

# 当前 Checkpoint schema 版本（§17.1）；不兼容版本拒绝直接加载，须显式迁移
SCHEMA_VERSION = "1.1"


def _merge_history(current: list[Any], update: list[Any]) -> list[Any]:
    """合并节点并行产生的 append-only 列表，同时兼容现有 full-list 节点返回值。

    Native Checkpointer 的新 turn 通过空列表显式清空本轮历史字段；普通节点
    不返回这些字段时不会触发 reducer，因此不会误清空已有历史。
    """
    if not current:
        return list(update)
    if not update:
        return []
    common = 0
    limit = min(len(current), len(update))
    while common < limit and current[common] == update[common]:
        common += 1
    if common == len(current):
        return list(update)
    if common == len(update):
        return list(current)
    return [*current, *update[common:]]


def _last_value(current: Any, update: Any) -> Any:
    """允许并行理解分支写入中间 next_action；汇合节点随后覆盖它。"""
    del current
    return update


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
    prompt_version: str | None
    taxonomy_version: str | None
    retrieval_index_version: str | None
    fusion_version: str | None
    rerank_version: str | None
    token_usage: dict[str, int] | None
    cache_hit: bool | None
    interrupt_kind: str | None
    memory_operation_count: int | None
    checkpoint_migration: str | None
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


class NativeTurnInput(TypedDict, total=False):
    """native graph 新 turn 的增量输入；不覆盖跨 turn 保留字段。"""

    schema_version: str
    session_id: str
    request_id: str
    turn_id: str
    trace_id: str
    current_request: Required[AgentRequest]
    previous_state: None
    image_ref: ImageRef | None
    selected_option_id: str | None
    intent_patch: IntentPatch | None
    conflicts: list[ConflictRecord]
    retrieval_query: RetrievalQuery | None
    candidates: list[RetrievalCandidate]
    retrieval_attempts: int
    retrieval_fallback_used: bool
    relaxation_attempted: bool
    relaxed_attributes: list[str]
    normalized_candidates: list[NormalizedCandidate]
    spu_clusters: list[list[int]]
    same_item_review_pairs: list[MatchPair]
    sku_groups: list[SkuGroup]
    ranked_groups: list[RankedGroup]
    clarification: Clarification | None
    evidence_bundle: EvidenceBundle | None
    explanation_text: str | None
    explanation_verified: bool
    response: AgentResponse | None
    memory_context: list[MemoryRecord]
    dirty_flags: dict[str, bool]
    retry_counters: dict[str, int]
    next_action: str
    completion_reason: CompletionReason | None
    is_resumed: bool
    resumed_node: str | None
    step_count: int
    interrupt_generation: int
    errors: list[ErrorRecord]
    node_events: list[NodeEventRecord]
    fallbacks: list[FallbackRecord]
    notices: list[str]
    pending_memory_mutations: list[MemoryMutation]
    agent_results: list[AgentResult]
    active_interrupt: AgentInterrupt | None
    resume_consumed: bool
    fusion_version: str | None
    rerank_version: str | None
    retrieval_index_version: str | None
    execution_context: AgentExecutionContext | None


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
    image_ref: ImageRef | None
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
    same_item_review_pairs: list[MatchPair]
    sku_groups: list[SkuGroup]
    # 输出
    ranked_groups: list[RankedGroup]
    clarification: Clarification | None
    evidence_bundle: EvidenceBundle | None
    explanation_text: str | None
    explanation_verified: bool
    response: AgentResponse | None
    notices: Annotated[list[str], _merge_history]
    keywords: list[str]
    # 控制
    dirty_flags: dict[str, bool]
    retry_counters: dict[str, int]
    next_action: Annotated[str, _last_value]
    completion_reason: CompletionReason | None
    is_resumed: bool
    resumed_node: str | None
    step_count: int
    interrupt_generation: int
    # 可观测性
    fallbacks: Annotated[list[FallbackRecord], _merge_history]
    errors: Annotated[list[ErrorRecord], _merge_history]
    node_events: Annotated[list[NodeEventRecord], _merge_history]
    # 二期工程化字段
    execution_context: AgentExecutionContext | None
    recent_turns: list[ConversationTurnSummary]
    memory_context: list[MemoryRecord]
    pending_memory_mutations: list[MemoryMutation]
    agent_results: list[AgentResult]
    active_interrupt: AgentInterrupt | None
    resume_consumed: bool
    fusion_version: str | None
    rerank_version: str | None
    retrieval_index_version: str | None


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
        same_item_review_pairs=[],
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
        interrupt_generation=0,
        node_events=[],
        fallbacks=[],
        errors=[],
        execution_context=None,
        recent_turns=[],
        memory_context=[],
        pending_memory_mutations=[],
        agent_results=[],
        active_interrupt=None,
        resume_consumed=False,
        fusion_version=None,
        rerank_version=None,
        retrieval_index_version=None,
    )


def mark_dirty(state: AgentState, *flags: str) -> None:
    for f in flags:
        state.setdefault("dirty_flags", {})[f] = True


def clean_dirty(state: AgentState, *flags: str) -> None:
    for f in flags:
        state.setdefault("dirty_flags", {})[f] = False


def merge_task_results(
    current: dict[str, AgentResultV2] | None,
    update: dict[str, AgentResultV2] | AgentResultV2,
) -> dict[str, AgentResultV2]:
    """Supervisor reducer：同 hash 重放幂等，不同 hash 拒绝静默覆盖。"""
    merged = dict(current or {})
    incoming = {update.task_id: update} if isinstance(update, AgentResultV2) else update
    for task_id, result in incoming.items():
        existing = merged.get(task_id)
        if existing is None:
            merged[task_id] = result
            continue
        if existing.output_hash != result.output_hash:
            raise TaskResultConflictError(
                f"task_id={task_id} 已存在不同 output_hash",
            )
    return merged


class SupervisorState(TypedDict, total=False):
    """Multi-Agent 公共规范状态；Specialist 不接收此类型。"""

    schema_version: str
    session_id: str
    request_id: str
    turn_id: str
    trace_id: str
    current_request: AgentRequest
    execution_context: AgentExecutionContext
    plan: ExecutionPlan
    task_records: dict[str, TaskRecord]
    task_results: Annotated[dict[str, AgentResultV2], merge_task_results]
    canonical_understanding: CanonicalUnderstanding
    active_interrupt: AgentInterrupt | None
    final_response: AgentResponse | None
    replan_count: int
    total_task_count: int
    budget_usage: SupervisorBudgetUsage
    notices: Annotated[list[str], _merge_history]
    events: Annotated[list[AgentEventRecord], _merge_history]
