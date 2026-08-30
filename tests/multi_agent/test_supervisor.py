"""Multi-Agent Supervisor 的并行 barrier、私有 Agent 和领域算法回归。"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest

from shijiajing_agent.adapters.langgraph_persistence import open_graph_checkpointer
from shijiajing_agent.config import Settings
from shijiajing_agent.contracts import (
    AgentExecutionContext,
    AgentRequest,
    AgentResume,
    AgentStatus,
    AgentTaskKind,
    IntentPatch,
    InterruptKind,
    MatchPair,
    MemoryApplyMode,
    MemoryDirective,
    MemoryOperation,
    NodeStatus,
    RetrievalTaskOutput,
    SpecialistAgentName,
    SupervisorPlanningInput,
)
from shijiajing_agent.facade import AgentFacade
from shijiajing_agent.multi_agent.agents.base import fixed_error, result_for
from shijiajing_agent.multi_agent.checkpoint import InMemoryMultiAgentCheckpoint
from shijiajing_agent.multi_agent.planner import DeterministicPlanner
from shijiajing_agent.multi_agent.registry import build_registry
from shijiajing_agent.multi_agent.supervisor import MultiAgentSupervisor

from .conftest import default_recognition, make_image, two_candidate_result


class _EchoPlanner:
    model_name = "planner-test"
    prompt_version = "test-v1"

    def __init__(self) -> None:
        self.create_calls = 0

    async def create_plan(self, request: SupervisorPlanningInput):
        self.create_calls += 1
        return request.base_plan or DeterministicPlanner().create_plan(
            request.request,
            context=request.execution_context,
            taxonomy_version=request.taxonomy_version,
        )


class _BrokenPlanner:
    model_name = "planner-test"
    prompt_version = "test-v1"

    async def create_plan(self, _request: SupervisorPlanningInput):
        raise RuntimeError("planner network unavailable")


class _InvalidPlanPlanner:
    model_name = "planner-test"
    prompt_version = "test-v1"

    async def create_plan(self, request: SupervisorPlanningInput):
        plan = DeterministicPlanner().create_plan(
            request.request,
            context=request.execution_context,
            taxonomy_version=request.taxonomy_version,
        )
        return plan.model_copy(
            update={
                "tasks": [
                    task for task in plan.tasks if task.task_kind is not AgentTaskKind.PARSE_INTENT
                ]
            }
        )


@pytest.mark.asyncio
async def test_multi_agent_text_path_uses_task_results_and_deterministic_retrieval(
    deps_factory: Any,
) -> None:
    deps, fakes = deps_factory()
    fakes["retrieval"].sequence = [two_candidate_result()]
    result = await MultiAgentSupervisor(deps).run(
        AgentRequest(session_id="multi", request_id="r1", text="索尼耳机")
    )
    assert result.response.status is AgentStatus.SUCCESS
    assert result.response.groups
    assert result.state["task_results"]
    assert any(
        item.task_kind is AgentTaskKind.PARSE_INTENT
        for item in result.state["task_results"].values()
    )
    assert any(
        item.task_kind is AgentTaskKind.RETRIEVE_AND_RANK
        for item in result.state["task_results"].values()
    )


@pytest.mark.asyncio
async def test_planner_outcome_is_traced_metered_and_not_recalled_on_checkpoint_replay(
    deps_factory: Any,
) -> None:
    settings = replace(
        Settings(), supervisor_planner_mode="active", supervisor_model="planner-test"
    )
    deps, fakes = deps_factory(settings)
    fakes["retrieval"].sequence = [two_candidate_result()]
    candidate = _EchoPlanner()
    deps.supervisor_planner = candidate
    assert deps.settings.supervisor_planner_mode == "active"
    assert deps.supervisor_planner is candidate
    checkpoint = InMemoryMultiAgentCheckpoint()
    supervisor = MultiAgentSupervisor(deps, checkpoint=checkpoint)
    request = AgentRequest(session_id="planner-audit", request_id="create-1", text="索尼耳机")

    first = await supervisor.run(request)
    assert first.response.status is AgentStatus.SUCCESS
    assert first.state["planning_outcome"].source == "model"
    assert first.state["planning_outcome"].validated is True
    assert candidate.create_calls == 1
    event_types = [event.event_type.value for event in fakes["trace"].events]
    assert "planner_call_started" in event_types
    assert "planner_proposal_received" in event_types
    assert "planner_plan_accepted" in event_types
    assert "plan_created" in event_types
    assert fakes["metrics"].counts["planner_call_total"] == 1
    assert fakes["metrics"].counts["planner_model_plan_accepted_total"] == 1
    assert first.state["planning_outcome"].plan_hash
    assert first.state["events"]
    assert all("raw_response" not in event.payload for event in first.state["events"])

    replay = await supervisor.run(request)
    assert replay.response.status is AgentStatus.SUCCESS
    assert candidate.create_calls == 1


@pytest.mark.asyncio
async def test_valid_shadow_plan_is_traced_as_validated_then_falls_back(
    deps_factory: Any,
) -> None:
    settings = replace(
        Settings(), supervisor_planner_mode="shadow", supervisor_model="planner-test"
    )
    deps, fakes = deps_factory(settings)
    fakes["retrieval"].sequence = [two_candidate_result()]
    candidate = _EchoPlanner()
    deps.supervisor_planner = candidate

    result = await MultiAgentSupervisor(deps).run(
        AgentRequest(session_id="planner-shadow", request_id="create-1", text="索尼耳机")
    )

    outcome = result.state["planning_outcome"]
    assert result.response.status is AgentStatus.SUCCESS
    assert outcome.validated is True
    assert outcome.accepted is False
    assert outcome.source == "deterministic"
    assert outcome.fallback_reason == "MODEL_PLAN_SHADOWED"
    event_types = [event.event_type.value for event in fakes["trace"].events]
    assert "planner_plan_accepted" in event_types
    assert "planner_plan_rejected" not in event_types
    assert "planner_fallback" in event_types
    assert fakes["metrics"].counts["planner_model_plan_accepted_total"] == 1
    assert fakes["metrics"].counts["planner_fallback_total"] == 1


@pytest.mark.asyncio
async def test_planner_fallback_is_observable_and_business_path_survives(
    deps_factory: Any,
) -> None:
    settings = replace(
        Settings(), supervisor_planner_mode="active", supervisor_model="planner-test"
    )
    deps, fakes = deps_factory(settings)
    fakes["retrieval"].sequence = [two_candidate_result()]
    deps.supervisor_planner = _BrokenPlanner()
    result = await MultiAgentSupervisor(deps).run(
        AgentRequest(session_id="planner-fallback", request_id="create-1", text="索尼耳机")
    )
    assert result.response.status is AgentStatus.SUCCESS
    assert fakes["metrics"].counts["planner_fallback_total"] == 1
    assert any(
        event.event_type.value == "planner_fallback" and event.error_code == "MODEL_NETWORK_ERROR"
        for event in fakes["trace"].events
    )


@pytest.mark.asyncio
async def test_invalid_model_plan_is_rejected_traced_and_falls_back(
    deps_factory: Any,
) -> None:
    settings = replace(
        Settings(), supervisor_planner_mode="active", supervisor_model="planner-test"
    )
    deps, fakes = deps_factory(settings)
    fakes["retrieval"].sequence = [two_candidate_result()]
    deps.supervisor_planner = _InvalidPlanPlanner()

    result = await MultiAgentSupervisor(deps).run(
        AgentRequest(session_id="planner-invalid", request_id="create-1", text="索尼耳机")
    )

    assert result.response.status is AgentStatus.SUCCESS
    assert result.state["planning_outcome"].source == "deterministic"
    assert result.state["planning_outcome"].validated is False
    assert result.state["planning_outcome"].accepted is False
    assert result.state["planning_outcome"].fallback_reason == "PLAN_VALIDATION_FAILED"
    assert any(task.task_kind is AgentTaskKind.PARSE_INTENT for task in result.plan.tasks)
    event_types = [event.event_type.value for event in fakes["trace"].events]
    assert "planner_proposal_received" in event_types
    assert "planner_plan_rejected" in event_types
    assert "planner_fallback" in event_types
    assert any(
        event.event_type.value == "planner_fallback"
        and event.error_code == "PLAN_VALIDATION_FAILED"
        for event in fakes["trace"].events
    )
    assert fakes["metrics"].counts["planner_fallback_total"] == 1
    assert fakes["metrics"].counts["planner_validation_rejected_total"] == 1


@pytest.mark.asyncio
async def test_multi_agent_missing_category_skips_retrieval(
    deps_factory: Any,
) -> None:
    deps, fakes = deps_factory()
    result = await MultiAgentSupervisor(deps).run(
        AgentRequest(session_id="multi", request_id="r2", text="帮我比个价")
    )
    assert result.response.status is AgentStatus.CLARIFICATION
    assert fakes["retrieval"].calls == 0
    retrieval = next(
        item
        for item in result.state["task_results"].values()
        if item.task_kind is AgentTaskKind.RETRIEVE_AND_RANK
    )
    assert retrieval.status.value == "skipped"


@pytest.mark.asyncio
async def test_facade_uses_supervisor_path(
    deps_factory: Any,
) -> None:
    deps, fakes = deps_factory(Settings())
    fakes["retrieval"].sequence = [two_candidate_result()]
    response = await AgentFacade(deps).run(
        AgentRequest(session_id="multi", request_id="r3", text="索尼耳机")
    )
    assert response.status is AgentStatus.SUCCESS


@pytest.mark.asyncio
async def test_supervisor_checkpoint_replay_skips_completed_agent_tasks(
    deps_factory: Any,
) -> None:
    deps, fakes = deps_factory()
    fakes["retrieval"].sequence = [two_candidate_result()]
    checkpoint = InMemoryMultiAgentCheckpoint()
    request = AgentRequest(session_id="multi", request_id="r4", text="索尼耳机")
    first = await MultiAgentSupervisor(deps, checkpoint=checkpoint).run(request)
    calls = fakes["retrieval"].calls
    second = await MultiAgentSupervisor(deps, checkpoint=checkpoint).run(request)
    assert first.response.status is AgentStatus.SUCCESS
    assert second.response.status is AgentStatus.SUCCESS
    assert fakes["retrieval"].calls == calls


@pytest.mark.asyncio
async def test_retryable_agent_failure_is_replanned_and_dispatched_with_send(
    deps_factory: Any,
) -> None:
    deps, fakes = deps_factory()
    fakes["retrieval"].sequence = [two_candidate_result()]
    delegate = build_registry(deps)

    class FailOnceRegistry:
        def __init__(self) -> None:
            self.retrieval_calls = 0

        async def dispatch(self, task: Any) -> Any:
            if task.agent_name is SpecialistAgentName.RETRIEVAL:
                self.retrieval_calls += 1
                if self.retrieval_calls == 1:
                    return result_for(
                        task,
                        status=NodeStatus.FAILED,
                        error=fixed_error(
                            "TEMPORARY_RETRIEVAL_FAILURE",
                            "temporary retrieval failure",
                            retryable=True,
                        ),
                    )
            return await delegate.dispatch(task)

    registry = FailOnceRegistry()
    outcome = await MultiAgentSupervisor(deps, registry=registry).run(
        AgentRequest(session_id="multi", request_id="retry-1", text="索尼耳机")
    )

    assert outcome.response.status is AgentStatus.SUCCESS
    assert registry.retrieval_calls == 2
    assert outcome.state["replan_count"] == 1
    assert any(":retry:2" in task_id for task_id in outcome.state["task_results"])


@pytest.mark.asyncio
async def test_multi_agent_clarification_resume_continues_original_plan(
    deps_factory: Any,
) -> None:
    settings = replace(Settings(), hitl_enabled=True)
    deps, fakes = deps_factory(settings)
    fakes["retrieval"].sequence = [two_candidate_result()]
    checkpoint = InMemoryMultiAgentCheckpoint()
    supervisor = MultiAgentSupervisor(deps, checkpoint=checkpoint)
    request = AgentRequest(session_id="multi-hitl", request_id="clarify-1", text="帮我比个价")

    paused = await supervisor.run(request, context=AgentExecutionContext(), pause_for_hitl=True)
    assert paused.interrupt is not None
    assert paused.interrupt.kind is InterruptKind.CLARIFICATION
    retrieval_calls_before_resume = fakes["retrieval"].calls

    resumed = await supervisor.resume(
        request.session_id,
        AgentResume(
            interrupt_id=paused.interrupt.interrupt_id,
            value={"action": "answer", "text": "索尼耳机"},
        ),
        AgentExecutionContext(),
    )
    assert resumed.response is not None
    assert resumed.response.status is AgentStatus.SUCCESS
    assert fakes["retrieval"].calls == retrieval_calls_before_resume + 1

    replay = await supervisor.resume(
        request.session_id,
        AgentResume(
            interrupt_id=paused.interrupt.interrupt_id,
            value={"action": "answer", "text": "索尼耳机"},
        ),
        AgentExecutionContext(),
    )
    assert replay.response is not None
    assert fakes["retrieval"].calls == retrieval_calls_before_resume + 1


@pytest.mark.asyncio
async def test_multi_agent_recognition_review_resume_does_not_rerun_intent(
    deps_factory: Any,
) -> None:
    settings = replace(Settings(), hitl_enabled=True)
    deps, fakes = deps_factory(settings)
    fakes["vision"].results = [default_recognition().model_copy(update={"overall_confidence": 0.4})]
    fakes["retrieval"].sequence = [two_candidate_result()]
    checkpoint = InMemoryMultiAgentCheckpoint()
    supervisor = MultiAgentSupervisor(deps, checkpoint=checkpoint)
    request = AgentRequest(session_id="multi-hitl", request_id="review-1", image=make_image())

    paused = await supervisor.run(request, context=AgentExecutionContext(), pause_for_hitl=True)
    assert paused.interrupt is not None
    assert paused.interrupt.kind is InterruptKind.RECOGNITION_REVIEW
    intent_calls = fakes["intent"].calls

    resumed = await supervisor.resume(
        request.session_id,
        AgentResume(
            interrupt_id=paused.interrupt.interrupt_id,
            value={"action": "approve"},
        ),
        AgentExecutionContext(),
    )
    assert resumed.response is not None
    assert resumed.response.status is AgentStatus.SUCCESS
    assert fakes["intent"].calls == intent_calls


@pytest.mark.asyncio
async def test_multi_agent_same_item_review_resume_reuses_retrieval_result(
    deps_factory: Any,
) -> None:
    settings = replace(Settings(), hitl_enabled=True)
    deps, fakes = deps_factory(settings)
    fakes["retrieval"].sequence = [two_candidate_result()]
    delegate = build_registry(deps)

    class ReviewRegistry:
        async def dispatch(self, task: Any) -> Any:
            result = await delegate.dispatch(task)
            if task.agent_name is SpecialistAgentName.RETRIEVAL and isinstance(
                result.output, RetrievalTaskOutput
            ):
                output = result.output.model_copy(
                    update={
                        "same_item_review_pairs": [
                            MatchPair(
                                offer_a_id="o-taobao",
                                offer_b_id="o-jd",
                                same_item_score=0.7,
                                verdict="review",
                            )
                        ]
                    }
                )
                return result_for(task, status=NodeStatus.SUCCESS, output=output)
            return result

    checkpoint = InMemoryMultiAgentCheckpoint()
    supervisor = MultiAgentSupervisor(deps, registry=ReviewRegistry(), checkpoint=checkpoint)
    request = AgentRequest(session_id="multi-hitl", request_id="same-item-1", text="索尼耳机")
    paused = await supervisor.run(request, context=AgentExecutionContext(), pause_for_hitl=True)
    assert paused.interrupt is not None
    assert paused.interrupt.kind is InterruptKind.SAME_ITEM_REVIEW
    assert fakes["retrieval"].calls == 1

    resumed = await supervisor.resume(
        request.session_id,
        AgentResume(
            interrupt_id=paused.interrupt.interrupt_id,
            value={"action": "accept"},
        ),
        AgentExecutionContext(),
    )
    assert resumed.response is not None
    assert resumed.response.status is AgentStatus.SUCCESS
    assert fakes["retrieval"].calls == 1


@pytest.mark.asyncio
async def test_multi_agent_memory_confirmation_has_single_authorized_commit(
    deps_factory: Any,
) -> None:
    settings = replace(Settings(), hitl_enabled=True)
    deps, fakes = deps_factory(settings)

    class FakeMemory:
        def __init__(self) -> None:
            self.commit_calls = 0

        async def recall(self, _owner: str, _query: Any) -> list[Any]:
            return []

        async def commit(self, _owner: str, mutations: list[Any]) -> list[Any]:
            self.commit_calls += 1
            return []

        async def list_memories(self, _owner: str) -> list[Any]:
            return []

        async def clear_owner(self, _owner: str, _mutation_id: str) -> None:
            return None

    memory = FakeMemory()
    deps.memory = memory
    fakes["intent"].results = [
        IntentPatch(
            category_id="headphone",
            memory_directives=[
                MemoryDirective(
                    operation=MemoryOperation.UPSERT,
                    memory_key="max_price",
                    value=1000,
                    apply_mode=MemoryApplyMode.CONSTRAINT_DEFAULT,
                )
            ],
        )
    ]
    fakes["retrieval"].sequence = [two_candidate_result()]
    checkpoint = InMemoryMultiAgentCheckpoint()
    supervisor = MultiAgentSupervisor(deps, checkpoint=checkpoint)
    request = AgentRequest(
        session_id="multi-hitl",
        request_id="memory-1",
        text="记住以后买耳机预算 1000 元",
    )
    context = AgentExecutionContext(memory_enabled=True, memory_owner_id="owner-1")

    paused = await supervisor.run(request, context=context, pause_for_hitl=True)
    assert paused.interrupt is not None
    assert paused.interrupt.kind is InterruptKind.MEMORY_CONFIRMATION
    assert memory.commit_calls == 0

    resumed = await supervisor.resume(
        request.session_id,
        AgentResume(
            interrupt_id=paused.interrupt.interrupt_id,
            value={"action": "approve"},
        ),
        context,
    )
    assert resumed.response is not None
    assert resumed.response.status is AgentStatus.SUCCESS
    assert memory.commit_calls == 1

    replay = await supervisor.resume(
        request.session_id,
        AgentResume(
            interrupt_id=paused.interrupt.interrupt_id,
            value={"action": "approve"},
        ),
        context,
    )
    assert replay.response is not None
    assert memory.commit_calls == 1


@pytest.mark.asyncio
async def test_multi_agent_native_checkpoint_restores_active_interrupt(
    deps_factory: Any, tmp_path: Any
) -> None:
    settings = replace(Settings(), hitl_enabled=True, checkpoint_dsn=str(tmp_path / "multi.db"))
    deps, fakes = deps_factory(settings)
    fakes["retrieval"].sequence = [two_candidate_result()]
    request = AgentRequest(session_id="multi-native", request_id="native-1", text="帮我比个价")
    async with open_graph_checkpointer(settings) as saver:
        from shijiajing_agent.multi_agent.checkpoint import LangGraphMultiAgentCheckpoint

        checkpoint = LangGraphMultiAgentCheckpoint(saver)
        supervisor = MultiAgentSupervisor(deps, checkpoint=checkpoint)
        paused = await supervisor.run(request, context=AgentExecutionContext(), pause_for_hitl=True)
        assert paused.interrupt is not None
        restored = await checkpoint.load_active(request.session_id)
        assert restored is not None
        resumed = await MultiAgentSupervisor(deps, checkpoint=checkpoint).resume(
            request.session_id,
            AgentResume(
                interrupt_id=paused.interrupt.interrupt_id,
                value={"action": "answer", "text": "索尼耳机"},
            ),
            AgentExecutionContext(),
        )
        assert resumed.response is not None
        assert resumed.response.status is AgentStatus.SUCCESS
