"""Multi-Agent Supervisor 的并行 barrier、私有 Agent 和旧业务算法回归。"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest

from shijiajing_agent.config import Settings
from shijiajing_agent.contracts import AgentRequest, AgentStatus, AgentTaskKind
from shijiajing_agent.facade import AgentFacade
from shijiajing_agent.multi_agent.checkpoint import InMemoryMultiAgentCheckpoint
from shijiajing_agent.multi_agent.supervisor import MultiAgentSupervisor

from .conftest import two_candidate_result


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
async def test_facade_mode_switch_keeps_workflow_default_and_routes_multi_agent(
    deps_factory: Any,
) -> None:
    settings = replace(Settings(), orchestration_mode="multi_agent")
    deps, fakes = deps_factory(settings)
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
