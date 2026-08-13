"""失败注入测试（方案 §21.5）。

Trace sink 失败不阻断业务结果，但必须增加本地错误计数；
Checkpoint 失败必须阻断成功提交。
"""

from __future__ import annotations

from typing import Any

import pytest

from shijiajing_agent.contracts import AgentRequest, AgentStatus
from shijiajing_agent.state import AgentState
from tests.workflow.conftest import (
    FakeCheckpoint,
    FakeMetrics,
    FakeTraceSink,
    two_candidate_result,
)


class FailOnSaveCheckpoint(FakeCheckpoint):
    """Checkpoint 写入失败注入（磁盘满 / 数据库故障）。"""

    async def save(self, session_id: str, state: AgentState, expected_version: int | None) -> int:
        raise RuntimeError("disk full")


class FailOnLoadCheckpoint(FakeCheckpoint):
    """Checkpoint 读取失败注入。"""

    async def load(self, session_id: str) -> tuple[AgentState, int] | None:
        raise RuntimeError("connection refused")


class FailTraceSink(FakeTraceSink):
    """trace sink 不可用注入。"""

    async def emit(self, event: Any) -> None:
        raise RuntimeError("collector down")


@pytest.fixture
def agent_request() -> AgentRequest:
    return AgentRequest(
        session_id="fault-session",
        request_id="fault-req-1",
        text="索尼耳机 预算2000以内",
    )


class TestCheckpointFaults:
    async def test_checkpoint_save_failure_blocks_success(
        self, deps_factory, facade_factory, agent_request: AgentRequest
    ) -> None:
        """§21.5：Checkpoint 写入失败 → 本轮不得返回 success。"""
        deps, fakes = deps_factory(checkpoint=FailOnSaveCheckpoint())
        facade = facade_factory(deps)
        response = await facade.run(agent_request)
        assert response.status == AgentStatus.FAILED
        assert "状态存储不可用" in response.message
        # 失败路径仍保留 trace（TURN_STARTED + TURN_FAILED）
        events = fakes["trace"].events
        assert [e.event_type.value for e in events] == ["turn_started", "turn_failed"]
        assert fakes["metrics"].counts.get("agent_turn_total") == 1

    async def test_checkpoint_load_failure_returns_failed(
        self, deps_factory, facade_factory, agent_request: AgentRequest
    ) -> None:
        """§21.5：Checkpoint 读取失败 → CHECKPOINT_UNAVAILABLE 失败响应。"""
        deps, fakes = deps_factory(checkpoint=FailOnLoadCheckpoint())
        facade = facade_factory(deps)
        response = await facade.run(agent_request)
        assert response.status == AgentStatus.FAILED
        assert "状态存储不可用" in response.message
        assert fakes["metrics"].counts.get("agent_turn_total") == 1

    async def test_session_conflict_replayed_once_then_failed(
        self, deps_factory, facade_factory, agent_request: AgentRequest
    ) -> None:
        """§17.3：乐观版本冲突整轮最多重放一次；第二次冲突返回 SESSION_CONFLICT。"""
        checkpoint = FakeCheckpoint()
        checkpoint.conflict_on_save = True
        deps, _ = deps_factory(checkpoint=checkpoint)
        facade = facade_factory(deps)
        response = await facade.run(agent_request)
        assert response.status == AgentStatus.FAILED
        assert "会话状态冲突" in response.message

    async def test_idempotent_request_returns_cached_without_rerun(
        self, deps_factory, facade_factory, agent_request: AgentRequest
    ) -> None:
        """§17.2：重复 request_id 返回已保存响应，不重复调用外部依赖。"""
        deps, fakes = deps_factory()
        fakes["retrieval"].sequence = [two_candidate_result()]
        facade = facade_factory(deps)
        first = await facade.run(agent_request)
        assert first.status != AgentStatus.FAILED
        # 种子已保存响应后，同一 request_id 的重复请求直接命中缓存
        same = AgentRequest(
            session_id=agent_request.session_id,
            request_id=agent_request.request_id,
            text="索尼耳机 预算2000以内",
        )
        second = await facade.run(same)
        assert second.request_id == first.request_id
        # 第二次只读了 checkpoint，未重新走图（无新增 TURN_STARTED）
        turn_started = [e for e in fakes["trace"].events if e.event_type.value == "turn_started"]
        assert len(turn_started) == 1


class TestTraceSinkFault:
    async def test_trace_sink_failure_does_not_block_business(
        self, deps_factory, facade_factory, agent_request: AgentRequest
    ) -> None:
        """§21.5：trace sink 不可用 → 业务照常完成，本地错误计数增加。"""
        deps, fakes = deps_factory(trace=FailTraceSink())
        fakes["retrieval"].sequence = [two_candidate_result()]
        facade = facade_factory(deps)
        response = await facade.run(agent_request)
        assert response.status == AgentStatus.SUCCESS
        assert fakes["metrics"].counts.get("trace_sink_failure_total", 0) >= 2

    async def test_metrics_failure_does_not_block_business(
        self, deps_factory, facade_factory, agent_request: AgentRequest
    ) -> None:
        """指标输出失败不阻断业务（§20 失败语义）。"""

        class FailingMetrics(FakeMetrics):
            def inc(
                self, name: str, labels: dict[str, str] | None = None, value: float = 1.0
            ) -> None:
                raise RuntimeError("scrape endpoint down")

        deps, fakes = deps_factory(metrics=FailingMetrics())
        fakes["retrieval"].sequence = [two_candidate_result()]
        facade = facade_factory(deps)
        response = await facade.run(agent_request)
        assert response.status == AgentStatus.SUCCESS
