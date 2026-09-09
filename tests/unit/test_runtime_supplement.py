"""主 Agent 按需补查的准入、预算、去重和原子合并测试。"""

from __future__ import annotations

import pytest

from shijiajing_agent.agent_runtime.contracts import (
    ActionKind,
    ActionStatus,
    AnswerAction,
    SearchAndCompareAction,
    SupplementQueryProposal,
    SupplementSearchAction,
)
from shijiajing_agent.agent_runtime.runtime import MainAgentRuntime
from shijiajing_agent.config import Settings
from shijiajing_agent.contracts import AgentRequest
from shijiajing_agent.ports.retrieval import RetrievalResult
from tests.agent_runtime.conftest import candidate, make_deps, two_candidate_result


def _supplement(text: str = "英文补查") -> SupplementSearchAction:
    return SupplementSearchAction(
        gap_id="recall_window_truncated",
        query_proposals=[SupplementQueryProposal(text=text)],
    )


def _crowded_result() -> RetrievalResult:
    return RetrievalResult(
        candidates=[candidate(f"crowded-{index}", price=1000.0 + index) for index in range(61)],
        total_found=61,
    )


@pytest.mark.asyncio
async def test_direct_supplement_uses_explicit_queries_and_real_call_count(taxonomy) -> None:
    deps, fakes = make_deps(taxonomy, Settings(main_agent_model="fake-main"))
    fakes["retrieval"].sequence = [
        RetrievalResult(candidates=[], total_found=0),
        two_candidate_result(),
        two_candidate_result(),
    ]
    fakes["agent_decision"].action_queue = [
        SearchAndCompareAction(),
        SupplementSearchAction(
            gap_id="no_qualified_candidates",
            query_proposals=[
                SupplementQueryProposal(text="英文补查"),
                SupplementQueryProposal(text="品牌别名补查"),
            ],
        ),
        AnswerAction(),
    ]

    outcome = await MainAgentRuntime(deps).run(
        AgentRequest(session_id="supplement", request_id="r1", text="索尼耳机")
    )

    assert outcome.response.status.value == "success"
    assert outcome.state.supplement_stage_used is True
    assert len(outcome.state.supplement_query_fingerprints) == 2
    assert len(outcome.state.query_fingerprints) == 3
    assert len(outcome.state.recall_pool) == 2
    assert len(outcome.state.last_candidates) == 2
    assert outcome.state.retrieval_assessment["stage"] == "supplement"
    assert fakes["retrieval"].calls == 3
    assert fakes["rewrite"].calls == 1, "补查不得再次触发 query rewrite"
    assert [item.kind for item in outcome.state.actions] == [
        ActionKind.SEARCH_AND_COMPARE,
        ActionKind.SUPPLEMENT_SEARCH,
        ActionKind.ANSWER,
    ]
    assert outcome.state.usage.retrieval_calls == 3


@pytest.mark.asyncio
async def test_supplement_budget_failure_does_not_commit_stage(taxonomy) -> None:
    settings = Settings(
        main_agent_model="fake-main",
        main_agent_max_retrieval_calls=2,
    )
    deps, fakes = make_deps(taxonomy, settings)
    fakes["retrieval"].sequence = [RetrievalResult(candidates=[], total_found=0)]
    fakes["agent_decision"].action_queue = [
        SearchAndCompareAction(),
        SupplementSearchAction(
            gap_id="no_qualified_candidates",
            query_proposals=[
                SupplementQueryProposal(text="补查一"),
                SupplementQueryProposal(text="补查二"),
            ],
        ),
    ]

    outcome = await MainAgentRuntime(deps).run(
        AgentRequest(session_id="supplement-budget", request_id="r1", text="索尼耳机")
    )

    assert outcome.state.supplement_stage_used is False
    assert outcome.state.supplement_query_fingerprints == []
    assert fakes["retrieval"].calls == 1
    supplement_record = next(
        item for item in outcome.state.actions if item.kind is ActionKind.SUPPLEMENT_SEARCH
    )
    assert supplement_record.status is ActionStatus.FAILED
    assert supplement_record.error_code == "BUDGET_EXCEEDED"


@pytest.mark.asyncio
async def test_empty_supplement_preserves_initial_results(taxonomy) -> None:
    settings = Settings(
        main_agent_model="fake-main",
        same_item_accept_threshold=1.0,
        same_item_review_threshold=0.5,
    )
    deps, fakes = make_deps(taxonomy, settings)
    fakes["retrieval"].sequence = [
        _crowded_result(),
        RetrievalResult(candidates=[], total_found=0),
    ]
    fakes["agent_decision"].action_queue = [
        SearchAndCompareAction(),
        _supplement(),
        AnswerAction(),
    ]

    outcome = await MainAgentRuntime(deps).run(
        AgentRequest(session_id="supplement-empty", request_id="r1", text="索尼耳机")
    )

    assert outcome.response.status.value == "success"
    assert outcome.state.supplement_stage_used is True
    assert outcome.state.supplement_no_progress_count == 1
    assert outcome.state.ranked_groups
    assert outcome.state.last_tool_status == "success"
    assert outcome.state.usage.retrieval_calls == 2
    assert outcome.state.actions[1].usage.retrieval_calls == 1


@pytest.mark.asyncio
async def test_repeated_supplement_fingerprint_is_rejected(taxonomy) -> None:
    settings = Settings(
        main_agent_model="fake-main",
        same_item_accept_threshold=1.0,
        same_item_review_threshold=0.5,
    )
    deps, fakes = make_deps(taxonomy, settings)
    fakes["retrieval"].sequence = [_crowded_result()]
    fakes["agent_decision"].action_queue = [
        SearchAndCompareAction(),
        SupplementSearchAction(
            gap_id="recall_window_truncated",
            query_proposals=[SupplementQueryProposal(text="索尼耳机")],
        ),
        AnswerAction(),
    ]

    outcome = await MainAgentRuntime(deps).run(
        AgentRequest(session_id="supplement-duplicate", request_id="r1", text="索尼耳机")
    )

    assert outcome.response.status.value == "success"
    assert fakes["retrieval"].calls == 1
    assert outcome.state.supplement_stage_used is False
    assert outcome.state.actions[1].status is ActionStatus.FAILED
    assert outcome.state.actions[1].error_code == "ACTION_FAILED"
