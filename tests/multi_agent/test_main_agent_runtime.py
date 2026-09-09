"""主 Agent：简单路径、动作约束、按需关闭与 HITL 恢复契约。"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from shijiajing_agent.agent_runtime.checkpoint import InMemoryAgentRuntimeCheckpoint
from shijiajing_agent.agent_runtime.contracts import (
    ActionKind,
    AnswerAction,
    AskUserAction,
    DecisionResult,
    DelegateResearchAction,
    DelegateVerificationAction,
    MainAction,
    SearchAndCompareAction,
    SubagentActionKind,
    SubagentDecisionResult,
    SubagentFinishAction,
    SubagentGetOfferDetailsAction,
    SubagentSearchAction,
)
from shijiajing_agent.config import Settings
from shijiajing_agent.contracts import (
    AgentExecutionContext,
    AgentRequest,
    AgentResume,
    AgentStatus,
    InterruptKind,
)
from shijiajing_agent.facade import AgentFacade
from shijiajing_agent.ports.retrieval import RetrievalResult
from tests.multi_agent.conftest import make_offer, two_candidate_result


class AdaptiveDecision:
    """根据观察选动作，验证 runtime 确实把工具结果送回同一主 Agent。"""

    def __init__(self) -> None:
        self.calls = 0
        self.actions: list[MainAction] = []

    async def decide(
        self, observation: Any, allowed_actions: tuple[ActionKind, ...]
    ) -> DecisionResult:
        self.calls += 1
        if not observation.evidence_summary and "no_qualified_candidates" not in observation.gaps:
            action: MainAction = SearchAndCompareAction(query_text="索尼耳机")
        else:
            action = AnswerAction(
                result_ids=[str(observation.evidence_summary[0]["candidate_id"])],
                evidence_ids=[str(observation.evidence_summary[0]["evidence_id"])],
            )
        assert action.kind in allowed_actions
        self.actions.append(action)
        return DecisionResult(action=action)


class ClarifyingDecision:
    async def decide(
        self, observation: Any, allowed_actions: tuple[ActionKind, ...]
    ) -> DecisionResult:
        assert ActionKind.ASK_USER in allowed_actions
        return DecisionResult(
            action=AskUserAction(missing_fields=["category_id"], question_type="missing_category")
        )


class ResearchingMainDecision:
    async def decide(
        self, observation: Any, allowed_actions: tuple[ActionKind, ...]
    ) -> DecisionResult:
        if not observation.evidence_summary and "no_qualified_candidates" not in observation.gaps:
            action: MainAction = SearchAndCompareAction(query_text="索尼耳机")
        else:
            action = DelegateResearchAction(
                objective="根据型号别名寻找更多候选",
                gap_code="alias_search",
            )
        assert action.kind in allowed_actions
        return DecisionResult(action=action)


class ResearchDecision:
    def __init__(self) -> None:
        self.calls = 0

    async def decide(
        self, observation: Any, allowed_actions: tuple[SubagentActionKind, ...]
    ) -> SubagentDecisionResult:
        self.calls += 1
        if not observation.queries:
            action = SubagentSearchAction(query_text="WH-1000XM5 降噪耳机")
        else:
            action = SubagentFinishAction(status="complete", end_reason="candidate_found")
        assert action.kind in allowed_actions
        return SubagentDecisionResult(action=action)


class VerificationMainDecision:
    def __init__(self, disputed_field: str = "model") -> None:
        self.disputed_field = disputed_field

    async def decide(
        self, observation: Any, allowed_actions: tuple[ActionKind, ...]
    ) -> DecisionResult:
        if not observation.evidence_summary:
            action: MainAction = SearchAndCompareAction(query_text="索尼耳机")
        elif observation.gaps:
            action = AnswerAction(
                result_ids=[str(observation.evidence_summary[0]["candidate_id"])],
                evidence_ids=[str(observation.evidence_summary[0]["evidence_id"])],
            )
        else:
            offers = observation.evidence_summary[:2]
            action = DelegateVerificationAction(
                candidate_ids=[str(item["offer_id"]) for item in offers],
                disputed_fields=[self.disputed_field],
                evidence_ids=[str(item["evidence_id"]) for item in offers],
            )
        assert action.kind in allowed_actions
        return DecisionResult(action=action)


class DetailPort:
    def __init__(self, *, changed_model: str | None = None) -> None:
        self.calls = 0
        self.changed_model = changed_model

    async def get_details(self, offer_ids: list[str], fields: list[str]) -> list[Any]:
        self.calls += 1
        return [
            make_offer(
                offer_id,
                platform="jd" if offer_id == "o-jd" else "taobao",
                price=1999.0 if offer_id == "o-jd" else 1899.0,
                model=(
                    self.changed_model
                    if offer_id == "o-jd" and self.changed_model
                    else "WH-1000XM5"
                ),
            )
            for offer_id in offer_ids
        ]


class VerificationDecision:
    def __init__(self) -> None:
        self.calls = 0

    async def decide(
        self, observation: Any, allowed_actions: tuple[SubagentActionKind, ...]
    ) -> SubagentDecisionResult:
        self.calls += 1
        if SubagentActionKind.GET_OFFER_DETAILS in allowed_actions and not observation.queries:
            action = SubagentGetOfferDetailsAction(
                candidate_ids=[item["candidate_id"] for item in observation.candidate_summary],
                fields=list(observation.focus_fields),
            )
        else:
            action = SubagentFinishAction(status="complete", end_reason="verified")
        assert action.kind in allowed_actions
        return SubagentDecisionResult(action=action)


@pytest.mark.asyncio
async def test_main_agent_simple_path_uses_zero_subagents(
    deps_factory: Any,
) -> None:
    settings = replace(Settings(), execution_mode="main", main_agent_model="fake-main")
    deps, fakes = deps_factory(settings)
    decision = AdaptiveDecision()
    deps.agent_decision = decision
    fakes["retrieval"].sequence = [two_candidate_result()]

    response = await AgentFacade(deps).run(
        AgentRequest(session_id="main", request_id="simple", text="索尼耳机")
    )

    assert response.status is AgentStatus.SUCCESS
    assert fakes["retrieval"].calls == 1
    assert decision.calls == 2
    assert all(
        action.kind not in {ActionKind.DELEGATE_RESEARCH, ActionKind.DELEGATE_VERIFICATION}
        for action in decision.actions
    )


@pytest.mark.asyncio
async def test_main_agent_missing_category_can_pause_and_resume(
    deps_factory: Any,
) -> None:
    settings = replace(
        Settings(), execution_mode="main", main_agent_model="fake-main", hitl_enabled=True
    )
    deps, _ = deps_factory(settings)
    deps.agent_decision = ClarifyingDecision()
    checkpoint = InMemoryAgentRuntimeCheckpoint()
    deps.agent_checkpoint = checkpoint
    facade = AgentFacade(deps)

    paused = await facade.start(
        AgentRequest(session_id="main-hitl", request_id="clarify", text="帮我比价"),
        AgentExecutionContext(),
    )
    assert paused.interrupt is not None
    assert paused.interrupt.kind is InterruptKind.CLARIFICATION

    # 只验证恢复契约和版本化状态；新的决策仍会继续由同一主 Agent 处理。
    resumed = await facade.resume(
        "main-hitl",
        AgentResume(
            interrupt_id=paused.interrupt.interrupt_id,
            value={"action": "answer", "text": "索尼耳机"},
        ),
        AgentExecutionContext(),
    )
    assert resumed.response is not None
    assert resumed.response.status is AgentStatus.NO_RESULTS


@pytest.mark.asyncio
async def test_main_agent_reuses_structured_session_context_on_next_turn(
    deps_factory: Any,
) -> None:
    settings = replace(Settings(), execution_mode="main", main_agent_model="fake-main")
    deps, fakes = deps_factory(settings)
    decision = AdaptiveDecision()
    deps.agent_decision = decision
    fakes["retrieval"].sequence = [two_candidate_result(), two_candidate_result()]
    facade = AgentFacade(deps)

    first = await facade.run(
        AgentRequest(
            session_id="cross-turn",
            request_id="first",
            text="索尼耳机 3000 元以内 京东 黑色",
        )
    )
    second = await facade.run(
        AgentRequest(session_id="cross-turn", request_id="second", text="换白色")
    )

    assert first.status is AgentStatus.SUCCESS
    assert second.status is AgentStatus.SUCCESS
    constraints = second.effective_constraints
    assert constraints is not None
    assert constraints.max_price.value == 3000.0
    assert constraints.platforms.value == ["jd"]
    assert constraints.colors.value == ["白色"]
    assert fakes["retrieval"].calls == 2


@pytest.mark.asyncio
async def test_research_subagent_changes_query_and_parent_revalidates_results(
    deps_factory: Any,
) -> None:
    settings = replace(
        Settings(),
        execution_mode="main_with_subagents",
        main_agent_model="fake-main",
        research_subagent_enabled=True,
    )
    deps, fakes = deps_factory(settings)
    main_decision = ResearchingMainDecision()
    research_decision = ResearchDecision()
    deps.agent_decision = main_decision
    deps.research_decision = research_decision
    fakes["retrieval"].sequence = [
        RetrievalResult(candidates=[], total_found=0),
        two_candidate_result(),
    ]

    facade = AgentFacade(deps)
    response = await facade.run(
        AgentRequest(session_id="research", request_id="complex", text="索尼耳机")
    )

    assert response.status is AgentStatus.SUCCESS
    assert research_decision.calls == 2
    assert fakes["retrieval"].calls == 2
    assert fakes["retrieval"].last_query is not None
    assert fakes["retrieval"].last_query.query_text == "WH-1000XM5 降噪耳机"
    assert facade._main_runtime is not None
    result = facade._main_runtime._local_states[("research", "complex")].subagent_results[0]
    assert result.queries == ["WH-1000XM5 降噪耳机"]
    assert result.evidence_ids
    assert result.facts


@pytest.mark.asyncio
async def test_verification_subagent_cannot_override_hard_model_conflict(
    deps_factory: Any,
) -> None:
    settings = replace(
        Settings(),
        execution_mode="main_with_subagents",
        main_agent_model="fake-main",
        verification_subagent_enabled=True,
    )
    deps, fakes = deps_factory(settings)
    deps.agent_decision = VerificationMainDecision()
    deps.verification_decision = VerificationDecision()
    deps.offer_details = DetailPort(changed_model="WH-1000XM4")
    fakes["retrieval"].sequence = [two_candidate_result()]
    facade = AgentFacade(deps)

    response = await facade.run(
        AgentRequest(session_id="verification", request_id="conflict", text="索尼耳机")
    )

    assert response.status is AgentStatus.SUCCESS
    assert deps.offer_details.calls == 1
    assert facade._main_runtime is not None
    state = facade._main_runtime._local_states[("verification", "conflict")]
    assert state.subagent_results[0].recommendation == "not_comparable"
    assert state.gaps == ["not_comparable"]


@pytest.mark.asyncio
async def test_verification_subagent_reports_unknown_promotion_as_insufficient_evidence(
    deps_factory: Any,
) -> None:
    settings = replace(
        Settings(),
        execution_mode="main_with_subagents",
        main_agent_model="fake-main",
        verification_subagent_enabled=True,
    )
    deps, fakes = deps_factory(settings)
    deps.agent_decision = VerificationMainDecision("discount_eligibility")
    deps.verification_decision = VerificationDecision()
    deps.offer_details = DetailPort()
    fakes["retrieval"].sequence = [two_candidate_result()]
    facade = AgentFacade(deps)

    response = await facade.run(
        AgentRequest(session_id="verification", request_id="unknown", text="索尼耳机")
    )

    assert response.status is AgentStatus.SUCCESS
    assert facade._main_runtime is not None
    state = facade._main_runtime._local_states[("verification", "unknown")]
    assert state.subagent_results[0].recommendation == "insufficient_evidence"
    assert "discount_eligibility" in state.gaps


@pytest.mark.asyncio
async def test_verification_subagent_stays_closed_without_details_port(
    deps_factory: Any,
) -> None:
    settings = replace(
        Settings(),
        execution_mode="main_with_subagents",
        main_agent_model="fake-main",
        verification_subagent_enabled=True,
    )
    deps, fakes = deps_factory(settings)
    deps.agent_decision = AdaptiveDecision()
    deps.verification_decision = VerificationDecision()
    fakes["retrieval"].sequence = [two_candidate_result()]

    facade = AgentFacade(deps)
    response = await facade.run(
        AgentRequest(session_id="verification-off", request_id="simple", text="索尼耳机")
    )

    assert response.status is AgentStatus.SUCCESS
    assert any("核验 subagent 已关闭" in notice for notice in response.notices)
    assert facade._main_runtime is not None
    assert facade._main_runtime._local_states[("verification-off", "simple")].subagent_results == []


def test_main_action_is_strict_and_discriminated() -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(MainAction).validate_python({"kind": "answer", "unexpected": True})
