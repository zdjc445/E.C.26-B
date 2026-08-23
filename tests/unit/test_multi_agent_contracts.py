"""受控层级式 Multi-Agent 协议与计划门禁测试。"""

from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

from shijiajing_agent.contracts import (
    AgentResultV2,
    AgentTaskInput,
    AgentTaskKind,
    AgentTaskUsage,
    AgentTaskV2,
    ExecutionPlan,
    IntentTaskInput,
    IntentTaskOutput,
    NodeStatus,
    SpecialistAgentName,
    content_hash,
)
from shijiajing_agent.errors import CapabilityDeniedError, TaskResultConflictError
from shijiajing_agent.multi_agent.capabilities import validate_capability
from shijiajing_agent.multi_agent.planner import DeterministicPlanner, PlanValidator
from shijiajing_agent.state import merge_task_results


def _task(*, task_id: str = "t1") -> AgentTaskV2:
    return AgentTaskV2(
        plan_id="p1",
        task_id=task_id,
        agent_name=SpecialistAgentName.INTENT,
        task_kind=AgentTaskKind.PARSE_INTENT,
        idempotency_key=f"id:{task_id}",
        deadline_at="2026-08-23T00:00:00+00:00",
        input=IntentTaskInput(text="耳机"),
    )


def _result(task: AgentTaskV2, marker: str = "same") -> AgentResultV2:
    output = IntentTaskOutput(patch=None, missing_fields=[marker])
    return AgentResultV2(
        plan_id=task.plan_id,
        task_id=task.task_id,
        agent_name=task.agent_name,
        task_kind=task.task_kind,
        status=NodeStatus.SUCCESS,
        output=output,
        usage=AgentTaskUsage(),
        output_hash=content_hash(output.model_dump(mode="json")),
    )


def test_discriminated_input_rejects_unknown_and_mismatched_payloads() -> None:
    adapter = TypeAdapter(AgentTaskInput)
    parsed = adapter.validate_python({"kind": "intent", "text": "耳机"})
    assert isinstance(parsed, IntentTaskInput)
    with pytest.raises(ValidationError):
        adapter.validate_python({"kind": "intent", "image": "not-allowed"})
    with pytest.raises(ValidationError):
        AgentTaskV2(
            plan_id="p1",
            task_id="bad",
            agent_name=SpecialistAgentName.RECOGNITION,
            task_kind=AgentTaskKind.RECOGNIZE,
            idempotency_key="id:bad",
            deadline_at="now",
            input=IntentTaskInput(text="耳机"),
        )


def test_result_merge_is_idempotent_and_conflicts_are_typed() -> None:
    task = _task()
    result = _result(task)
    merged = merge_task_results({}, result)
    assert merge_task_results(merged, result) == merged
    with pytest.raises(TaskResultConflictError) as exc_info:
        merge_task_results(merged, _result(task, "different"))
    assert exc_info.value.code.value == "TASK_RESULT_CONFLICT"


def test_execution_plan_validates_dag_and_deterministic_skip() -> None:
    with pytest.raises(ValidationError):
        ExecutionPlan(
            tasks=[
                _task(task_id="a").model_copy(update={"depends_on": ["b"]}),
                _task(task_id="b").model_copy(update={"depends_on": ["a"]}),
            ],
            plan_id="p1",
        )
    from shijiajing_agent.contracts import AgentRequest

    plan = DeterministicPlanner().create_plan(
        AgentRequest(session_id="s", request_id="r", text="耳机")
    )
    PlanValidator().validate(plan)
    assert not any(task.agent_name is SpecialistAgentName.RECOGNITION for task in plan.tasks)
    assert any(task.task_kind is AgentTaskKind.RETRIEVE_AND_RANK for task in plan.tasks)


def test_capability_allowlist_rejects_forbidden_memory_access() -> None:
    validate_capability(SpecialistAgentName.RECOGNITION, "vision")
    with pytest.raises(CapabilityDeniedError):
        validate_capability(SpecialistAgentName.RECOGNITION, "memory_store")
