"""模型 Planner shadow 报告生成与脱敏测试。"""

from __future__ import annotations

import json
from typing import ClassVar

import pytest

from shijiajing_agent.config import Settings
from shijiajing_agent.contracts import AgentTaskKind
from shijiajing_agent.multi_agent.planner_shadow import (
    validate_planner_shadow_report_payload,
)
from shijiajing_agent.tools.run_planner_shadow import (
    _load_cases,
    build_planner_shadow_report,
)


class _ValidDifferentPlanner:
    model_name = "planner-test"
    prompt_version = "planner-test-v1"
    repair_count = 0
    token_usage: ClassVar[dict[str, int]] = {
        "prompt_tokens": 10,
        "completion_tokens": 5,
        "total_tokens": 15,
    }
    proposal_hash = "a" * 64
    action_count = 1

    async def create_plan(self, request):
        plan = request.base_plan
        assert plan is not None
        return plan.model_copy(
            update={
                "tasks": [
                    task for task in plan.tasks if task.task_kind is not AgentTaskKind.EXPLAIN
                ]
            }
        )


def test_load_cases_accepts_frozen_multi_agent_shape(tmp_path) -> None:
    dataset = tmp_path / "planner.jsonl"
    dataset.write_text(
        json.dumps(
            {
                "id": "planner-1",
                "subgraph_input": {"text": "索尼耳机，预算 1000"},
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    cases = _load_cases(dataset)

    assert len(cases) == 1
    assert cases[0][0] == "planner-1"
    assert cases[0][1].text == "索尼耳机，预算 1000"


@pytest.mark.asyncio
async def test_shadow_report_proves_validation_without_executing_candidate_plan() -> None:
    settings = Settings(supervisor_planner_mode="shadow", supervisor_model="planner-test")
    cases = _load_cases_from_payload([{"id": "planner-1", "text": "索尼耳机，预算 1000"}])

    report = await build_planner_shadow_report(
        cases,
        settings=settings,
        candidate=_ValidDifferentPlanner(),
        data_version="frozen-test-v1",
    )

    assert validate_planner_shadow_report_payload(report) is None
    assert report["gate_passed"] is True
    assert report["planner"]["sample_count"] == 1
    assert report["planner"]["plan_difference_count"] == 1
    assert report["planner"]["token_total"] == 15
    assert report["planner"]["fallback_count"] == 1
    case = report["cases"][0]
    assert case["execution_plan_preserved"] is True
    assert case["planner_outcome"]["validated"] is True
    assert case["planner_outcome"]["accepted"] is False
    assert case["planner_outcome"]["fallback_reason"] == "MODEL_PLAN_SHADOWED"
    assert case["planner_outcome"]["candidate_plan_hash"] != case["planner_outcome"]["plan_hash"]
    serialized = json.dumps(report, ensure_ascii=False)
    assert "索尼耳机" not in serialized
    assert "raw_response" not in serialized


def _load_cases_from_payload(payloads):
    from shijiajing_agent.contracts import AgentRequest

    return [
        (
            payload["id"],
            AgentRequest(
                session_id="planner-shadow",
                request_id=payload["id"],
                text=payload["text"],
            ),
        )
        for payload in payloads
    ]
