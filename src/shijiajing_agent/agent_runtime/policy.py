"""动作权限、委派准入和确定性降级策略。"""

from __future__ import annotations

from dataclasses import dataclass

from shijiajing_agent.agent_runtime.contracts import (
    ActionKind,
    AnswerAction,
    AskUserAction,
    DecisionObservation,
    DelegateResearchAction,
    DelegateVerificationAction,
    InspectEvidenceAction,
    MainAction,
    MainRuntimeState,
    SearchAndCompareAction,
)
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
        elif isinstance(action, InspectEvidenceAction):
            missing = set(action.evidence_ids) - set(state.evidence)
            if missing:
                raise ActionRejectedError("inspect_evidence 引用了未注册的 evidence_id")
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
    if state.evidence:
        actions.insert(1, ActionKind.INSPECT_EVIDENCE)
    if research_enabled:
        actions.insert(2, ActionKind.DELEGATE_RESEARCH)
    if verification_enabled:
        actions.insert(3, ActionKind.DELEGATE_VERIFICATION)
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
    return DecisionObservation(
        objective_summary=objective,
        constraints_version=state.constraints_version,
        constraints=constraints,
        recognition=state.understanding.recognition,
        understanding=state.understanding,
        evidence_summary=summary,
        gaps=list(state.gaps),
        conflicts=list(state.conflicts),
        available_actions=list(actions),
        usage=state.usage,
        remaining_budget=state.budget,
    )


__all__ = [
    "ActionGuard",
    "ActionRejectedError",
    "DelegationDecision",
    "DelegationPolicy",
    "allowed_actions_for",
    "observation_for",
]
