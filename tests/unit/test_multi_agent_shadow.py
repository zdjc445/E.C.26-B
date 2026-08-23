"""Multi-Agent 灰度对照与发布报告门禁测试。"""

from __future__ import annotations

import pytest

from shijiajing_agent.contracts import AgentRequest, AgentResponse, AgentStatus
from shijiajing_agent.multi_agent.shadow import (
    run_shadow_suite,
    validate_shadow_report_payload,
)


def _response(request: AgentRequest, status: AgentStatus) -> AgentResponse:
    return AgentResponse(
        session_id=request.session_id,
        request_id=request.request_id,
        turn_id="turn",
        status=status,
        trace_id="trace",
    )


@pytest.mark.asyncio
async def test_shadow_suite_compares_same_business_invariants() -> None:
    request = AgentRequest(session_id="shadow", request_id="r1", text="耳机")

    async def legacy_runner(item: AgentRequest) -> AgentResponse:
        return _response(item, AgentStatus.NO_RESULTS)

    async def multi_agent_runner(item: AgentRequest) -> AgentResponse:
        return _response(item, AgentStatus.NO_RESULTS)

    report = await run_shadow_suite(
        [("frozen-1", request)],
        legacy_runner=legacy_runner,
        multi_agent_runner=multi_agent_runner,
    )
    payload = report.as_dict()

    assert report.gate_passed is True
    assert validate_shadow_report_payload(payload) is None


@pytest.mark.asyncio
async def test_shadow_suite_fails_when_business_status_differs() -> None:
    request = AgentRequest(session_id="shadow", request_id="r2", text="耳机")

    async def legacy_runner(item: AgentRequest) -> AgentResponse:
        return _response(item, AgentStatus.NO_RESULTS)

    async def multi_agent_runner(item: AgentRequest) -> AgentResponse:
        return _response(item, AgentStatus.FAILED)

    report = await run_shadow_suite(
        [("frozen-2", request)],
        legacy_runner=legacy_runner,
        multi_agent_runner=multi_agent_runner,
    )

    assert report.gate_passed is False
    assert report.cases[0].differences == ("status",)
    assert validate_shadow_report_payload(report.as_dict()) == ("shadow 报告 gate_passed 不为 true")
