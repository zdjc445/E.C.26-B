"""模型 Supervisor Planner 的契约、目录和物化安全边界。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from shijiajing_agent.contracts import AgentRequest, ExecutionPlanPatch, SupervisorPlanningInput
from shijiajing_agent.errors import PlanValidationError
from shijiajing_agent.multi_agent.planner import (
    DeterministicPlanner,
    GuardedSupervisorPlanner,
    PlanValidator,
    apply_plan_patch,
)
from shijiajing_agent.multi_agent.planner_catalog import build_action_catalog
from shijiajing_agent.multi_agent.planner_contracts import PlannerAction, PlannerProposal
from shijiajing_agent.multi_agent.planner_materializer import PlanMaterializer


def _base_plan():
    request = AgentRequest(session_id="planner-test", request_id="create-1", text="索尼耳机")
    return DeterministicPlanner().create_plan(request)


class _Candidate:
    def __init__(self, plan):
        self.plan = plan
        self.create_calls = 0

    async def create_plan(self, _request):
        self.create_calls += 1
        return self.plan


def test_planner_proposal_forbids_extra_fields_and_invalid_shape() -> None:
    with pytest.raises(ValidationError):
        PlannerProposal.model_validate(
            {
                "base_plan_id": "plan-1",
                "actions": [
                    {
                        "action_id": "keep:x",
                        "action": "keep",
                        "reason_code": "baseline",
                        "unexpected": True,
                    }
                ],
            }
        )
    with pytest.raises(ValidationError):
        PlannerAction(
            action_id="add:template-explanation-fallback",
            action="add_template",
            target_task_id="plan-1:explanation",
            reason_code="fallback",
        )


def test_catalog_materializer_accepts_only_allowlisted_actions() -> None:
    plan = _base_plan()
    catalog = build_action_catalog(plan)
    proposal = PlannerProposal(
        base_plan_id=plan.plan_id,
        actions=[
            PlannerAction(
                action_id="skip:not-in-catalog",
                action="skip",
                target_task_id=f"{plan.plan_id}:explanation",
                reason_code="fallback",
            )
        ],
    )
    with pytest.raises(PlanValidationError, match="ACTION_NOT_ALLOWED"):
        PlanMaterializer().materialize_plan(plan, catalog, proposal)


def test_skip_task_ids_are_applied_and_dependent_skip_is_rejected() -> None:
    plan = _base_plan()
    explanation_id = f"{plan.plan_id}:explanation"
    materializer = PlanMaterializer()
    catalog = build_action_catalog(plan)
    proposal = PlannerProposal(
        base_plan_id=plan.plan_id,
        actions=[
            PlannerAction(
                action_id=f"skip:{explanation_id}",
                action="skip",
                target_task_id=explanation_id,
                reason_code="not_needed",
            )
        ],
    )
    updated = materializer.materialize_plan(plan, catalog, proposal)
    assert explanation_id not in {task.task_id for task in updated.tasks}

    retrieval_id = f"{plan.plan_id}:retrieval"
    unsafe = PlannerProposal(
        base_plan_id=plan.plan_id,
        actions=[
            PlannerAction(
                action_id=f"skip:{retrieval_id}",
                action="skip",
                target_task_id=retrieval_id,
                reason_code="not_needed",
            )
        ],
    )
    with pytest.raises(PlanValidationError):
        materializer.materialize_plan(plan, catalog, unsafe)


def test_retry_replace_removes_old_task_and_rewires_dependencies() -> None:
    plan = _base_plan()
    retrieval_id = f"{plan.plan_id}:retrieval"
    replacement_id = f"{retrieval_id}:retry:2"
    updated = apply_plan_patch(
        plan,
        ExecutionPlanPatch(
            retry_task_ids=[retrieval_id],
            add_tasks=[
                next(task for task in plan.tasks if task.task_id == retrieval_id).model_copy(
                    update={
                        "task_id": replacement_id,
                        "parent_task_id": retrieval_id,
                        "attempt": 2,
                        "idempotency_key": f"{retrieval_id}:retry:2",
                    }
                )
            ],
            replace_task_ids={retrieval_id: replacement_id},
        ),
    )
    task_ids = {task.task_id for task in updated.tasks}
    assert retrieval_id not in task_ids
    assert replacement_id in task_ids
    explanation = next(task for task in updated.tasks if task.task_id.endswith(":explanation"))
    assert explanation.depends_on == [replacement_id]


def test_template_materializer_generates_system_owned_task_input() -> None:
    plan = _base_plan()
    catalog = build_action_catalog(plan)
    target_id = f"{plan.plan_id}:retrieval"
    proposal = PlannerProposal(
        base_plan_id=plan.plan_id,
        actions=[
            PlannerAction(
                action_id="add:template-retrieval-recognition-relaxation",
                action="add_template",
                target_task_id=target_id,
                template_id="template-retrieval-recognition-relaxation",
                reason_code="recognition_relaxation",
            )
        ],
    )
    updated = PlanMaterializer().materialize_plan(plan, catalog, proposal)
    replacement = next(task for task in updated.tasks if "recognition-relaxation" in task.task_id)
    assert replacement.input.model_dump(mode="json").get("recognition") is None
    assert replacement.task_id.startswith(plan.plan_id)


def test_plan_validator_normalizes_internal_key_error_to_plan_validation_error() -> None:
    invalid = _base_plan().model_copy(deep=True)
    invalid.tasks[0] = invalid.tasks[0].model_copy(
        update={"task_kind": "retrieval.retrieve_and_rank"}
    )
    with pytest.raises(PlanValidationError):
        PlanValidator().validate(invalid)


@pytest.mark.asyncio
async def test_shadow_mode_validates_model_but_executes_deterministic_plan() -> None:
    plan = _base_plan()
    candidate = _Candidate(plan.model_copy(update={"tasks": plan.tasks[:-1]}))
    guarded = GuardedSupervisorPlanner(DeterministicPlanner(), candidate, mode="shadow")
    request = SupervisorPlanningInput(
        request=AgentRequest(session_id="planner-test", request_id="create-1", text="索尼耳机"),
        taxonomy_version="unknown",
    )
    result = await guarded.create_plan(request)
    assert len(result.tasks) == len(plan.tasks)
    assert candidate.create_calls == 1
    assert guarded.last_outcome is not None
    assert guarded.last_outcome.validated is True
    assert guarded.last_outcome.fallback_reason == "MODEL_PLAN_SHADOWED"
    assert guarded.last_outcome.source == "deterministic"
    assert guarded.last_outcome.candidate_plan_hash is not None
