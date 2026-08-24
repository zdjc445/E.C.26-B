"""Ark Supervisor Planner 结构化输出与安全物化契约。"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from shijiajing_agent.adapters.ark_models import ModelCallRecord
from shijiajing_agent.adapters.ark_supervisor_planner import ArkSupervisorPlanner
from shijiajing_agent.contracts import (
    AgentRequest,
    AgentTaskKind,
    SupervisorPlanningInput,
    SupervisorReplanningInput,
)
from shijiajing_agent.multi_agent.planner import DeterministicPlanner


def _base_plan(taxonomy: Any):
    return DeterministicPlanner().create_plan(
        AgentRequest(session_id="ark-planner", request_id="create-1", text="索尼耳机"),
        taxonomy_version=taxonomy.taxonomy_version,
    )


async def test_ark_supervisor_planner_accepts_allowlisted_proposal(
    taxonomy: Any, ark_client: Any, ark_settings: Any
) -> None:
    plan = _base_plan(taxonomy)
    explanation_id = f"{plan.plan_id}:explanation"
    response = (
        '{"schema_version":"1.0",'
        f'"base_plan_id":"{plan.plan_id}","actions":[{{"action_id":"skip:{explanation_id}",'
        '"action":"skip","target_task_id":"'
        f'{explanation_id}","reason_code":"not_needed"}}]}}'
    )
    client, server = ark_client([response])
    settings = replace(ark_settings, supervisor_model="supervisor-test")
    planner = ArkSupervisorPlanner(client, taxonomy, settings)
    updated = await planner.create_plan(
        SupervisorPlanningInput(
            request=AgentRequest(session_id="ark-planner", request_id="create-1", text="索尼耳机"),
            taxonomy_version=taxonomy.taxonomy_version,
        )
    )
    assert explanation_id not in {task.task_id for task in updated.tasks}
    assert server.requests[0]["messages"][0]["content"].startswith(
        "你是受控 Multi-Agent Supervisor Planner"
    )
    assert planner.proposal_hash is not None
    assert planner.prompt_version == "supervisor-create-v1"
    await client.close()


async def test_ark_supervisor_planner_repairs_invalid_json_once(
    taxonomy: Any, ark_client: Any, ark_settings: Any
) -> None:
    plan = _base_plan(taxonomy)
    valid = f'{{"base_plan_id":"{plan.plan_id}","actions":[]}}'
    records: list[ModelCallRecord] = []
    client, server = ark_client(
        ['{"base_plan_id":"wrong","actions":[],"extra":true}', valid],
        on_call=records.append,
        max_model_repairs=1,
    )
    settings = replace(
        ark_settings,
        supervisor_model="supervisor-test",
        supervisor_planner_max_repairs=1,
    )
    planner = ArkSupervisorPlanner(client, taxonomy, settings)
    result = await planner.create_plan(
        SupervisorPlanningInput(
            request=AgentRequest(session_id="ark-planner", request_id="create-1", text="索尼耳机"),
            taxonomy_version=taxonomy.taxonomy_version,
        )
    )
    assert result.plan_id == plan.plan_id
    assert len(server.requests) == 2
    assert records[0].node == "supervisor_planner"
    assert records[0].repair_count == 1
    assert planner.repair_count == 1
    assert planner.token_usage["total_tokens"] > 0
    await client.close()


async def test_ark_supervisor_planner_revise_only_retries_failed_task(
    taxonomy: Any, ark_client: Any, ark_settings: Any
) -> None:
    plan = _base_plan(taxonomy)
    retrieval_id = next(
        task.task_id for task in plan.tasks if task.task_kind is AgentTaskKind.RETRIEVE_AND_RANK
    )
    response = (
        '{"schema_version":"1.0",'
        f'"base_plan_id":"{plan.plan_id}","actions":[{{"action_id":"retry:{retrieval_id}",'
        '"action":"retry",'
        f'"target_task_id":"{retrieval_id}","reason_code":"retryable_failure"}}]}}'
    )
    client, _ = ark_client([response])
    settings = replace(ark_settings, supervisor_model="supervisor-test")
    planner = ArkSupervisorPlanner(client, taxonomy, settings)
    patch = await planner.revise_plan(
        SupervisorReplanningInput(
            plan=plan,
            failed_task_ids=[retrieval_id],
            reason_code="retryable_task_failure",
        )
    )
    assert patch.retry_task_ids == [retrieval_id]
    assert patch.replace_task_ids[retrieval_id].endswith(":retry:2")
    await client.close()
