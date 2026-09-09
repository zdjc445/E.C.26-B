"""动作权限、委派准入和确定性降级策略。"""

from __future__ import annotations

from dataclasses import dataclass

from shijiajing_agent.agent_runtime.contracts import (
    ActionKind,
    ActionStatus,
    AnswerAction,
    AskUserAction,
    DecisionObservation,
    DelegateResearchAction,
    DelegateVerificationAction,
    InspectEvidenceAction,
    MainAction,
    MainRuntimeState,
    RuntimeBudgetRemaining,
    SearchAndCompareAction,
    SupplementSearchAction,
)
from shijiajing_agent.contracts import AgentStatus
from shijiajing_agent.ports.agent_decision import OfferDetailPort


class ActionRejectedError(ValueError):
    """模型动作未通过运行时权限/上下文校验。"""


@dataclass(frozen=True)
class DelegationDecision:
    eligible: bool
    reason_code: str


class DelegationPolicy:
    def __init__(
        self,
        *,
        research_enabled: bool,
        verification_enabled: bool,
        offer_details: OfferDetailPort | None = None,
    ) -> None:
        self.research_enabled = research_enabled
        self.verification_enabled = verification_enabled
        self.offer_details = offer_details

    def research(
        self, state: MainRuntimeState, action: DelegateResearchAction
    ) -> DelegationDecision:
        if not self.research_enabled:
            return DelegationDecision(False, "research_disabled")
        if (
            state.understanding.constraints is None
            or not state.understanding.constraints.category_id.value
        ):
            return DelegationDecision(False, "missing_category")
        if not state.gaps and state.ranked_groups:
            return DelegationDecision(False, "no_independent_gap")
        if state.supplement_stage_used:
            return DelegationDecision(False, "supplement_stage_already_completed")
        if any(
            result.role.value == "research" and result.status.value != "failed"
            for result in state.subagent_results
        ):
            return DelegationDecision(False, "research_already_completed")
        if not action.objective.strip():
            return DelegationDecision(False, "empty_objective")
        return DelegationDecision(True, "eligible")

    def verification(
        self, state: MainRuntimeState, action: DelegateVerificationAction
    ) -> DelegationDecision:
        if not self.verification_enabled:
            return DelegationDecision(False, "verification_disabled")
        if self.offer_details is None:
            return DelegationDecision(False, "offer_details_unavailable")
        known = {candidate.offer.offer_id for candidate in state.last_candidates}
        if any(candidate_id not in known for candidate_id in action.candidate_ids):
            return DelegationDecision(False, "candidate_not_in_current_results")
        if any(evidence_id not in state.evidence for evidence_id in action.evidence_ids):
            return DelegationDecision(False, "evidence_not_registered")
        if not action.disputed_fields:
            return DelegationDecision(False, "disputed_fields_missing")
        if any(
            result.role.value == "verification" and result.status.value != "failed"
            for result in state.subagent_results
        ):
            return DelegationDecision(False, "verification_already_completed")
        return DelegationDecision(True, "eligible")


class ActionGuard:
    """只检查动作是否有资格执行，不根据模型文字猜测或改写用户约束。"""

    def __init__(self, delegation: DelegationPolicy) -> None:
        self._delegation = delegation

    def validate(
        self,
        action: MainAction,
        state: MainRuntimeState,
        *,
        allowed_actions: tuple[ActionKind, ...],
    ) -> None:
        if action.kind not in allowed_actions:
            raise ActionRejectedError(f"动作 {action.kind.value} 当前不可用")
        if isinstance(action, SearchAndCompareAction):
            constraints = state.understanding.constraints
            if constraints is None or not constraints.category_id.value:
                raise ActionRejectedError("检索前必须具备商品品类")
            if any(
                item.kind is ActionKind.SEARCH_AND_COMPARE
                and item.constraints_version == state.constraints_version
                and item.status is not ActionStatus.FAILED
                for item in state.actions
            ):
                raise ActionRejectedError("当前约束版本的首轮检索已完成")
        elif isinstance(action, SupplementSearchAction):
            constraints = state.understanding.constraints
            if constraints is None or not constraints.category_id.value:
                raise ActionRejectedError("补查前必须具备当前约束")
            if not state.retrieval_assessment:
                raise ActionRejectedError("补查前必须完成首轮检索评估")
            if not any(
                item.kind is ActionKind.SEARCH_AND_COMPARE
                and item.status is not ActionStatus.FAILED
                for item in state.actions
            ):
                raise ActionRejectedError("补查前必须完成首轮检索")
            if state.supplement_stage_used:
                raise ActionRejectedError("当前约束版本的补查阶段已消费")
            if action.gap_id not in state.gaps:
                raise ActionRejectedError("补查引用了当前不存在的检索缺口")
            missing_evidence = {
                evidence_id
                for proposal in action.query_proposals
                for evidence_id in proposal.evidence_refs
                if evidence_id not in state.evidence
            }
            if missing_evidence:
                raise ActionRejectedError("补查引用了未注册的 evidence_id")
        elif isinstance(action, InspectEvidenceAction):
            missing_evidence = set(action.evidence_ids) - set(state.evidence)
            if missing_evidence:
                raise ActionRejectedError("inspect_evidence 引用了未注册的 evidence_id")
            known_candidates = {
                candidate.offer.offer_id
                for candidate in (state.recall_pool or state.last_candidates)
            }
            if set(action.candidate_ids) - known_candidates:
                raise ActionRejectedError("inspect_evidence 引用了当前召回池之外的 candidate_id")
        elif isinstance(action, AnswerAction):
            known_groups = {item.group.group_id for item in state.ranked_groups}
            if any(item not in known_groups for item in action.result_ids):
                raise ActionRejectedError("answer 引用了当前结果之外的 result_id")
            if any(item not in state.evidence for item in action.evidence_ids):
                raise ActionRejectedError("answer 引用了未注册的 evidence_id")
            if not state.ranked_groups and not state.gaps:
                raise ActionRejectedError("没有可回答结果")
        elif isinstance(action, DelegateResearchAction):
            decision = self._delegation.research(state, action)
            if not decision.eligible:
                raise ActionRejectedError(decision.reason_code)
        elif isinstance(action, DelegateVerificationAction):
            decision = self._delegation.verification(state, action)
            if not decision.eligible:
                raise ActionRejectedError(decision.reason_code)
        elif isinstance(action, AskUserAction):
            if not action.missing_fields:
                raise ActionRejectedError("ask_user 缺少 missing_fields")
        else:
            if state.ranked_groups:
                raise ActionRejectedError("已有合格结果时不能声明 no_results")


class FallbackPolicy:
    """预算、模型或动作失败后的确定性响应选择，不重新切回旧引擎。"""

    @staticmethod
    def response_status(state: MainRuntimeState) -> tuple[AgentStatus, str]:
        constraints = state.understanding.constraints
        if constraints is None or not constraints.category_id.value:
            return AgentStatus.CLARIFICATION, "请补充商品品类后继续比价。"
        if state.ranked_groups:
            return AgentStatus.SUCCESS, "使用已验证结果返回确定性降级答复。"
        if state.last_tool_status == "failed":
            return AgentStatus.FAILED, "检索服务不可用，请稍后重试。"
        return AgentStatus.NO_RESULTS, "当前条件下没有符合要求的比价结果。"


def allowed_actions_for(
    state: MainRuntimeState,
    *,
    research_enabled: bool,
    verification_enabled: bool,
) -> tuple[ActionKind, ...]:
    actions: list[ActionKind] = [
        ActionKind.SEARCH_AND_COMPARE,
        ActionKind.ASK_USER,
        ActionKind.ANSWER,
        ActionKind.FINISH_NO_RESULTS,
    ]
    if state.evidence or state.recall_pool or state.last_candidates:
        actions.insert(1, ActionKind.INSPECT_EVIDENCE)
    if research_enabled:
        actions.insert(2, ActionKind.DELEGATE_RESEARCH)
    if verification_enabled:
        actions.insert(3, ActionKind.DELEGATE_VERIFICATION)
    if (
        state.retrieval_assessment is not None
        and any(
            item.kind is ActionKind.SEARCH_AND_COMPARE and item.status is not ActionStatus.FAILED
            for item in state.actions
        )
        and state.gaps
        and not state.supplement_stage_used
    ):
        actions.insert(1, ActionKind.SUPPLEMENT_SEARCH)
    return tuple(dict.fromkeys(actions))


def observation_for(
    state: MainRuntimeState, actions: tuple[ActionKind, ...]
) -> DecisionObservation:
    constraints = state.understanding.constraints
    category = constraints.category_id.value if constraints is not None else None
    objective = f"为当前购物目标完成检索与比较；品类={category or '未确定'}"
    summary = [
        {
            "evidence_id": item.evidence_id,
            "candidate_id": item.candidate_id,
            "offer_id": item.offer_id,
            "fields": {
                key: item.fields[key]
                for key in ("platform", "price", "brand", "model")
                if key in item.fields
            },
        }
        for item in list(state.evidence.values())[:10]
    ]
    remaining_tokens = max(
        0,
        state.budget.max_tokens - state.usage.input_tokens - state.usage.output_tokens,
    )
    reserved = state.reserved_usage
    remaining = RuntimeBudgetRemaining(
        max_decisions=max(
            0, state.budget.max_decisions - state.usage.decisions - reserved.decisions
        ),
        max_tool_calls=max(
            0, state.budget.max_tool_calls - state.usage.tool_calls - reserved.tool_calls
        ),
        max_retrieval_calls=max(
            0,
            state.budget.max_retrieval_calls
            - state.usage.retrieval_calls
            - reserved.retrieval_calls,
        ),
        max_db_search_attempts=max(
            0,
            state.budget.max_db_search_attempts
            - state.usage.db_search_attempts
            - reserved.db_search_attempts,
        ),
        max_embedding_calls=max(
            0,
            state.budget.max_embedding_calls
            - state.usage.embedding_calls
            - reserved.embedding_calls,
        ),
        max_model_calls=max(
            0, state.budget.max_model_calls - state.usage.model_calls - reserved.model_calls
        ),
        max_tokens=remaining_tokens,
        max_subagent_starts=max(
            0,
            state.budget.max_subagent_starts
            - state.usage.subagent_starts
            - reserved.subagent_starts,
        ),
        max_seconds=max(0.0, state.budget.max_seconds - state.usage.elapsed_ms / 1000.0),
    )
    return DecisionObservation(
        objective_summary=objective,
        constraints_version=state.constraints_version,
        constraints=constraints,
        recognition=state.understanding.recognition,
        understanding=state.understanding,
        evidence_summary=summary,
        retrieval_assessment=state.retrieval_assessment,
        gaps=list(state.gaps)[:20],
        conflicts=list(state.conflicts)[:20],
        available_actions=list(actions),
        usage=state.usage,
        remaining_budget=remaining,
    )


__all__ = [
    "ActionGuard",
    "ActionRejectedError",
    "DelegationDecision",
    "DelegationPolicy",
    "FallbackPolicy",
    "allowed_actions_for",
    "observation_for",
]
