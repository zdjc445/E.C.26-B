"""主 Agent runtime 的严格内部契约。

这些模型与旧的 ``AgentTaskV2`` 分开，避免把旧 DAG 的任务语义和动态动作混在一起。
模型只能提出动作参数；版本、授权、预算和结果引用由 runtime 补齐或校验。
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from shijiajing_agent.contracts import (
    AgentInterrupt,
    AgentRequest,
    AgentResponse,
    CanonicalUnderstanding,
    MemoryMutation,
    RankedGroup,
    RecognitionResult,
    RetrievalCandidate,
    ShoppingConstraints,
)

_CODE = r"^[a-z][a-z0-9_.-]{0,63}$"


class ActionKind(StrEnum):
    SEARCH_AND_COMPARE = "search_and_compare"
    INSPECT_EVIDENCE = "inspect_evidence"
    DELEGATE_RESEARCH = "delegate_research"
    DELEGATE_VERIFICATION = "delegate_verification"
    ASK_USER = "ask_user"
    ANSWER = "answer"
    FINISH_NO_RESULTS = "finish_no_results"


class ActionStatus(StrEnum):
    PLANNED = "planned"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SubagentRole(StrEnum):
    RESEARCH = "research"
    VERIFICATION = "verification"


class SubagentStatus(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    NEEDS_USER_INPUT = "needs_user_input"
    FAILED = "failed"


class AgentRuntimeUsage(BaseModel):
    """所有运行时边界统一使用的可累加用量。"""

    model_config = ConfigDict(extra="forbid")

    decisions: int = Field(default=0, ge=0)
    model_calls: int = Field(default=0, ge=0)
    tool_calls: int = Field(default=0, ge=0)
    retrieval_calls: int = Field(default=0, ge=0)
    subagent_starts: int = Field(default=0, ge=0)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    elapsed_ms: float = Field(default=0.0, ge=0)

    def add(self, other: AgentRuntimeUsage) -> AgentRuntimeUsage:
        return AgentRuntimeUsage(
            decisions=self.decisions + other.decisions,
            model_calls=self.model_calls + other.model_calls,
            tool_calls=self.tool_calls + other.tool_calls,
            retrieval_calls=self.retrieval_calls + other.retrieval_calls,
            subagent_starts=self.subagent_starts + other.subagent_starts,
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            elapsed_ms=self.elapsed_ms + other.elapsed_ms,
        )


class RuntimeBudget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_decisions: int = Field(default=8, ge=1, le=100)
    max_tool_calls: int = Field(default=24, ge=1, le=200)
    max_retrieval_calls: int = Field(default=6, ge=1, le=100)
    max_model_calls: int = Field(default=32, ge=1, le=200)
    max_tokens: int = Field(default=100_000, ge=1, le=2_000_000)
    max_subagent_starts: int = Field(default=2, ge=0, le=20)
    max_seconds: float = Field(default=60.0, gt=0, le=3600)


class SearchAndCompareAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal[ActionKind.SEARCH_AND_COMPARE] = ActionKind.SEARCH_AND_COMPARE
    query_text: str = Field(default="", max_length=1000)
    soft_terms: list[str] = Field(default_factory=list[str], max_length=20)
    reason_code: str = Field(default="close_gap", pattern=_CODE)


class InspectEvidenceAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal[ActionKind.INSPECT_EVIDENCE] = ActionKind.INSPECT_EVIDENCE
    evidence_ids: list[str] = Field(min_length=1, max_length=20)
    fields: list[str] = Field(default_factory=list[str], max_length=20)
    reason_code: str = Field(default="inspect_gap", pattern=_CODE)


class DelegateResearchAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal[ActionKind.DELEGATE_RESEARCH] = ActionKind.DELEGATE_RESEARCH
    objective: str = Field(min_length=1, max_length=1000)
    gap_code: str = Field(min_length=1, max_length=64, pattern=_CODE)
    existing_query_refs: list[str] = Field(default_factory=list[str], max_length=10)
    reason_code: str = Field(default="complex_retrieval", pattern=_CODE)


class DelegateVerificationAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal[ActionKind.DELEGATE_VERIFICATION] = ActionKind.DELEGATE_VERIFICATION
    candidate_ids: list[str] = Field(min_length=1, max_length=20)
    disputed_fields: list[str] = Field(min_length=1, max_length=10)
    evidence_ids: list[str] = Field(default_factory=list[str], max_length=20)
    reason_code: str = Field(default="resolve_conflict", pattern=_CODE)


class AskUserAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal[ActionKind.ASK_USER] = ActionKind.ASK_USER
    missing_fields: list[str] = Field(min_length=1, max_length=20)
    question_type: str = Field(min_length=1, max_length=64, pattern=_CODE)
    option_refs: list[str] = Field(default_factory=list[str], max_length=20)
    reason_code: str = Field(default="missing_required_input", pattern=_CODE)


class AnswerAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal[ActionKind.ANSWER] = ActionKind.ANSWER
    result_ids: list[str] = Field(default_factory=list[str], max_length=20)
    evidence_ids: list[str] = Field(default_factory=list[str], max_length=50)
    focus: Literal["recommendation", "price", "evidence", "limitations"] = "recommendation"
    reason_code: str = Field(default="sufficient_evidence", pattern=_CODE)


class FinishNoResultsAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal[ActionKind.FINISH_NO_RESULTS] = ActionKind.FINISH_NO_RESULTS
    searched_scope: str = Field(min_length=1, max_length=500)
    reason_code: str = Field(min_length=1, max_length=64, pattern=_CODE)


MainAction = Annotated[
    SearchAndCompareAction
    | InspectEvidenceAction
    | DelegateResearchAction
    | DelegateVerificationAction
    | AskUserAction
    | AnswerAction
    | FinishNoResultsAction,
    Field(discriminator="kind"),
]


class DecisionObservation(BaseModel):
    """主 Agent 每轮可见的最小观察，不包含完整用户原文或模型原始响应。"""

    model_config = ConfigDict(extra="forbid")

    objective_summary: str = Field(min_length=1, max_length=2000)
    constraints_version: int = Field(default=1, ge=1)
    constraints: ShoppingConstraints | None = None
    recognition: RecognitionResult | None = None
    understanding: CanonicalUnderstanding | None = None
    evidence_summary: list[dict[str, Any]] = Field(
        default_factory=list[dict[str, Any]], max_length=10
    )
    gaps: list[str] = Field(default_factory=list[str], max_length=20)
    conflicts: list[str] = Field(default_factory=list[str], max_length=20)
    available_actions: list[ActionKind] = Field(min_length=1, max_length=7)
    usage: AgentRuntimeUsage = Field(default_factory=AgentRuntimeUsage)
    remaining_budget: RuntimeBudget = Field(default_factory=RuntimeBudget)


class DecisionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: MainAction
    usage: AgentRuntimeUsage = Field(default_factory=lambda: AgentRuntimeUsage(decisions=1))
    model: str | None = Field(default=None, max_length=128)
    prompt_version: str | None = Field(default=None, max_length=128)


class ActionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_id: str = Field(min_length=1, max_length=128)
    parent_action_id: str | None = Field(default=None, max_length=128)
    agent_id: str = Field(min_length=1, max_length=128)
    kind: ActionKind
    input_fingerprint: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    constraints_version: int = Field(ge=1)
    evidence_version: int = Field(ge=0)
    status: ActionStatus = ActionStatus.PLANNED
    result_refs: list[str] = Field(default_factory=list[str], max_length=50)
    usage: AgentRuntimeUsage = Field(default_factory=AgentRuntimeUsage)
    error_code: str | None = Field(default=None, max_length=64, pattern=r"^[A-Z][A-Z0-9_]*$")


class ToolObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["success", "fallback", "failed", "no_results"]
    result_refs: list[str] = Field(default_factory=list[str], max_length=50)
    new_evidence_ids: list[str] = Field(default_factory=list[str], max_length=50)
    gaps: list[str] = Field(default_factory=list[str], max_length=20)
    conflicts: list[str] = Field(default_factory=list[str], max_length=20)
    fallback_reason: str | None = Field(default=None, max_length=128)
    constraints_version: int = Field(ge=1)
    evidence_version: int = Field(ge=0)
    usage: AgentRuntimeUsage = Field(default_factory=AgentRuntimeUsage)


class SubagentBudget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_decisions: int = Field(default=4, ge=1, le=20)
    max_tool_calls: int = Field(default=6, ge=1, le=50)
    max_seconds: float = Field(default=30.0, gt=0, le=3600)
    max_tokens: int = Field(default=20_000, ge=1, le=500_000)


class SubagentActionKind(StrEnum):
    SEARCH_ONCE = "search_once"
    INSPECT_EVIDENCE = "inspect_evidence"
    COMPARE_CANDIDATES = "compare_candidates"
    GET_OFFER_DETAILS = "get_offer_details"
    FINISH = "finish"
    NEEDS_USER_INPUT = "needs_user_input"


class SubagentSearchAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal[SubagentActionKind.SEARCH_ONCE] = SubagentActionKind.SEARCH_ONCE
    query_text: str = Field(default="", max_length=1000)
    soft_terms: list[str] = Field(default_factory=list[str], max_length=20)
    reason_code: str = Field(default="close_gap", pattern=_CODE)


class SubagentInspectEvidenceAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal[SubagentActionKind.INSPECT_EVIDENCE] = SubagentActionKind.INSPECT_EVIDENCE
    evidence_ids: list[str] = Field(min_length=1, max_length=50)
    fields: list[str] = Field(default_factory=list[str], max_length=20)


class SubagentCompareCandidatesAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal[SubagentActionKind.COMPARE_CANDIDATES] = SubagentActionKind.COMPARE_CANDIDATES
    candidate_ids: list[str] = Field(min_length=1, max_length=50)


class SubagentGetOfferDetailsAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal[SubagentActionKind.GET_OFFER_DETAILS] = SubagentActionKind.GET_OFFER_DETAILS
    candidate_ids: list[str] = Field(min_length=1, max_length=20)
    fields: list[str] = Field(min_length=1, max_length=20)


class SubagentFinishAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal[SubagentActionKind.FINISH] = SubagentActionKind.FINISH
    status: Literal["complete", "partial", "failed"] = "complete"
    end_reason: str = Field(default="goal_satisfied", max_length=128, pattern=_CODE)


class SubagentNeedsUserInputAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal[SubagentActionKind.NEEDS_USER_INPUT] = SubagentActionKind.NEEDS_USER_INPUT
    unresolved_fields: list[str] = Field(min_length=1, max_length=20)
    end_reason: str = Field(default="needs_user_input", max_length=128, pattern=_CODE)


SubagentAction = Annotated[
    SubagentSearchAction
    | SubagentInspectEvidenceAction
    | SubagentCompareCandidatesAction
    | SubagentGetOfferDetailsAction
    | SubagentFinishAction
    | SubagentNeedsUserInputAction,
    Field(discriminator="kind"),
]


class SubagentTask(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(min_length=1, max_length=128)
    parent_action_id: str = Field(min_length=1, max_length=128)
    role: SubagentRole
    objective: str = Field(min_length=1, max_length=1000)
    constraints: ShoppingConstraints
    constraints_version: int = Field(ge=1)
    evidence_version: int = Field(ge=0)
    constraints_ref: str = Field(min_length=1, max_length=128)
    allowed_evidence_ids: list[str] = Field(default_factory=list[str], max_length=50)
    allowed_tools: list[str] = Field(min_length=1, max_length=4)
    budget: SubagentBudget = Field(default_factory=SubagentBudget)
    deadline_at: str = Field(min_length=1, max_length=64)


class SubagentObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(min_length=1, max_length=128)
    role: SubagentRole
    objective: str = Field(min_length=1, max_length=1000)
    constraints: ShoppingConstraints
    constraints_version: int = Field(ge=1)
    evidence_version: int = Field(ge=0)
    candidate_summary: list[dict[str, Any]] = Field(
        default_factory=list[dict[str, Any]], max_length=20
    )
    evidence_ids: list[str] = Field(default_factory=list[str], max_length=50)
    queries: list[str] = Field(default_factory=list[str], max_length=10)
    gaps: list[str] = Field(default_factory=list[str], max_length=20)
    conflicts: list[str] = Field(default_factory=list[str], max_length=20)
    available_actions: list[SubagentActionKind] = Field(min_length=1, max_length=6)
    usage: AgentRuntimeUsage = Field(default_factory=AgentRuntimeUsage)
    remaining_budget: SubagentBudget


class SubagentDecisionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: SubagentAction
    usage: AgentRuntimeUsage = Field(default_factory=lambda: AgentRuntimeUsage(decisions=1))
    model: str | None = Field(default=None, max_length=128)
    prompt_version: str | None = Field(default=None, max_length=128)


class VerifiedFact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str = Field(min_length=1, max_length=256)
    field: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_.-]*$")
    value: Any
    evidence_ids: list[str] = Field(min_length=1, max_length=20)


class SubagentResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(min_length=1, max_length=128)
    parent_action_id: str = Field(min_length=1, max_length=128)
    role: SubagentRole
    constraints_version: int = Field(ge=1)
    evidence_version: int = Field(ge=0)
    status: SubagentStatus
    candidate_ids: list[str] = Field(default_factory=list[str], max_length=50)
    queries: list[str] = Field(default_factory=list[str], max_length=10)
    facts: list[VerifiedFact] = Field(default_factory=list[VerifiedFact], max_length=100)
    evidence_ids: list[str] = Field(default_factory=list[str], max_length=100)
    unresolved_fields: list[str] = Field(default_factory=list[str], max_length=20)
    recommendation: Literal["comparable", "not_comparable", "insufficient_evidence"] | None = None
    end_reason: str = Field(min_length=1, max_length=128, pattern=_CODE)
    usage: AgentRuntimeUsage = Field(default_factory=AgentRuntimeUsage)

    @model_validator(mode="after")
    def _fact_references_are_declared(self) -> SubagentResult:
        declared = set(self.evidence_ids)
        if any(ref not in declared for fact in self.facts for ref in fact.evidence_ids):
            raise ValueError("Subagent fact 引用了未声明的 evidence_id")
        return self


class EvidenceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    candidate_id: str = Field(min_length=1, max_length=256)
    offer_id: str = Field(min_length=1, max_length=256)
    source_id: str = Field(min_length=1, max_length=256)
    data_version: str | None = Field(default=None, max_length=128)
    fields: dict[str, Any] = Field(default_factory=dict[str, Any], max_length=50)
    source_time: str | None = Field(default=None, max_length=64)
    status: Literal["observed", "verified", "insufficient"] = "observed"
    content_hash: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")


class EvidenceQualityReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    result_id: str = Field(min_length=1, max_length=256)
    constraints_version: int = Field(ge=1)
    comparable: bool
    evidence_ids: list[str] = Field(default_factory=list[str], max_length=100)
    missing_fields: list[str] = Field(default_factory=list[str], max_length=50)
    conflict_fields: list[str] = Field(default_factory=list[str], max_length=50)
    allowed_facts: list[VerifiedFact] = Field(default_factory=list[VerifiedFact], max_length=100)


class RuntimeSessionSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1, max_length=128)
    engine_version: str = Field(min_length=1, max_length=64)
    version: int = Field(default=1, ge=1)
    subject_id: str | None = Field(default=None, max_length=128)
    constraints: ShoppingConstraints | None = None
    recognition: RecognitionResult | None = None
    recent_turns: list[dict[str, Any]] = Field(default_factory=list[dict[str, Any]], max_length=6)


class MainRuntimeState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["agent-runtime-v1"] = "agent-runtime-v1"
    session_id: str = Field(min_length=1, max_length=128)
    request_id: str = Field(min_length=1, max_length=128)
    turn_id: str = Field(min_length=1, max_length=128)
    trace_id: str = Field(min_length=1, max_length=128)
    engine_version: str = Field(min_length=1, max_length=64)
    current_request: AgentRequest
    context: dict[str, Any] = Field(default_factory=dict[str, Any])
    understanding: CanonicalUnderstanding = Field(default_factory=CanonicalUnderstanding)
    constraints_version: int = Field(default=1, ge=1)
    evidence_version: int = Field(default=0, ge=0)
    evidence: dict[str, EvidenceRecord] = Field(
        default_factory=dict[str, EvidenceRecord], max_length=500
    )
    actions: list[ActionRecord] = Field(default_factory=list[ActionRecord], max_length=100)
    subagent_results: list[SubagentResult] = Field(
        default_factory=list[SubagentResult], max_length=20
    )
    usage: AgentRuntimeUsage = Field(default_factory=AgentRuntimeUsage)
    budget: RuntimeBudget = Field(default_factory=RuntimeBudget)
    gaps: list[str] = Field(default_factory=list[str], max_length=20)
    conflicts: list[str] = Field(default_factory=list[str], max_length=20)
    seen_fingerprints: list[str] = Field(default_factory=list[str], max_length=100)
    no_progress_count: int = Field(default=0, ge=0)
    ranked_groups: list[RankedGroup] = Field(default_factory=list[RankedGroup], max_length=100)
    last_candidates: list[RetrievalCandidate] = Field(
        default_factory=list[RetrievalCandidate], max_length=200
    )
    pending_mutations: list[MemoryMutation] = Field(
        default_factory=list[MemoryMutation], max_length=20
    )
    memory_authorized: bool = False
    active_interrupt: AgentInterrupt | None = None
    final_response: AgentResponse | None = None
    pending_response: AgentResponse | None = None
    resume_history: list[str] = Field(default_factory=list[str], max_length=20)
    completed_interrupts: list[str] = Field(default_factory=list[str], max_length=20)
    interrupt_generation: int = Field(default=0, ge=0)
    last_tool_status: str | None = Field(default=None, max_length=32)
    notices: list[str] = Field(default_factory=list[str], max_length=50)


__all__ = [
    "ActionKind",
    "ActionRecord",
    "ActionStatus",
    "AgentRuntimeUsage",
    "AnswerAction",
    "AskUserAction",
    "DecisionObservation",
    "DecisionResult",
    "DelegateResearchAction",
    "DelegateVerificationAction",
    "EvidenceQualityReport",
    "EvidenceRecord",
    "FinishNoResultsAction",
    "InspectEvidenceAction",
    "MainAction",
    "MainRuntimeState",
    "RuntimeBudget",
    "RuntimeSessionSnapshot",
    "SearchAndCompareAction",
    "SubagentAction",
    "SubagentActionKind",
    "SubagentBudget",
    "SubagentCompareCandidatesAction",
    "SubagentDecisionResult",
    "SubagentFinishAction",
    "SubagentGetOfferDetailsAction",
    "SubagentInspectEvidenceAction",
    "SubagentNeedsUserInputAction",
    "SubagentObservation",
    "SubagentResult",
    "SubagentRole",
    "SubagentSearchAction",
    "SubagentStatus",
    "SubagentTask",
    "ToolObservation",
    "VerifiedFact",
]
