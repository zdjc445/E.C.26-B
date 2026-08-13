"""可观测性适配器 contract 测试（方案 §20、§21.5 trace sink 不可用）。"""

from __future__ import annotations

import pytest

from shijiajing_agent.adapters.observability import PrometheusMetrics, StructlogTraceSink
from shijiajing_agent.contracts import AgentEvent, EventType, NodeStatus, now_iso


def make_event(**overrides) -> AgentEvent:
    payload = {
        "session_id": "s1",
        "request_id": "r1",
        "turn_id": "t:1",
        "trace_id": "tr:1",
        "event_type": EventType.TURN_STARTED,
        "timestamp": now_iso(),
        "node_name": "validate_input",
        "status": NodeStatus.SUCCESS,
        "duration_ms": 12.5,
    }
    payload.update(overrides)
    return AgentEvent(**payload)


def sample_value(registry, name: str, labels: dict[str, str] | None = None) -> float | None:
    """按实际采样名取值：prometheus-client 1.x 会给 Counter 名追加 ``_total``。"""
    value = registry.get_sample_value(name, labels)
    if value is None and not name.endswith("_total"):
        value = registry.get_sample_value(name + "_total", labels)
    return value


class TestPrometheusMetrics:
    def test_inc_creates_counter_and_increments(self) -> None:
        m = PrometheusMetrics()
        m.inc("agent_turn_total", {"status": "success"})
        m.inc("agent_turn_total", {"status": "success"})
        assert sample_value(m.registry, "agent_turn_total", {"status": "success"}) == 2.0

    def test_inc_without_labels(self) -> None:
        m = PrometheusMetrics()
        m.inc("checkpoint_failure_total")
        assert sample_value(m.registry, "checkpoint_failure_total") == 1.0

    def test_inc_custom_value(self) -> None:
        m = PrometheusMetrics()
        m.inc("retrieval_candidate_count", value=42.0)
        assert sample_value(m.registry, "retrieval_candidate_count") == 42.0

    def test_same_name_different_label_sets_rejected(self) -> None:
        """同一指标名的标签集必须一致（prometheus 注册表不允许重名），快速失败。"""
        m = PrometheusMetrics()
        m.inc("agent_turn_total", {"status": "success"})
        with pytest.raises(ValueError):
            m.inc("agent_turn_total", {"status": "failed", "workflow_version": "1.0"})

    def test_version_grouping_via_consistent_labels(self) -> None:
        """§20.2：按 workflow_version / prompt_version 等标签分组对比。"""
        m = PrometheusMetrics()
        m.inc("agent_turn_total", {"status": "success", "workflow_version": "1.0"})
        m.inc("agent_turn_total", {"status": "failed", "workflow_version": "1.0"})
        m.inc("agent_turn_total", {"status": "failed", "workflow_version": "2.0"})
        assert (
            sample_value(
                m.registry, "agent_turn_total", {"status": "success", "workflow_version": "1.0"}
            )
            == 1.0
        )
        assert (
            sample_value(
                m.registry, "agent_turn_total", {"status": "failed", "workflow_version": "1.0"}
            )
            == 1.0
        )
        assert (
            sample_value(
                m.registry, "agent_turn_total", {"status": "failed", "workflow_version": "2.0"}
            )
            == 1.0
        )

    def test_observe_records_histogram_observation(self) -> None:
        m = PrometheusMetrics()
        m.observe("agent_node_duration_ms", 50.0, {"node": "retrieve_candidates"})
        labels = {"node": "retrieve_candidates"}
        assert (
            sample_value(m.registry, "agent_node_duration_ms_bucket", {**labels, "le": "25.0"})
            == 0.0
        )
        assert (
            sample_value(m.registry, "agent_node_duration_ms_bucket", {**labels, "le": "100.0"})
            == 1.0
        )
        assert sample_value(m.registry, "agent_node_duration_ms_count", labels) == 1.0
        assert sample_value(m.registry, "agent_node_duration_ms_sum", labels) == 50.0

    def test_isolated_registry_by_default(self) -> None:
        """默认各自持有 CollectorRegistry，进程内重复注册不冲突。"""
        m1 = PrometheusMetrics()
        m2 = PrometheusMetrics()
        m1.inc("session_conflict_total")
        assert sample_value(m2.registry, "session_conflict_total") is None

    def test_custom_buckets(self) -> None:
        m = PrometheusMetrics(duration_buckets_ms=[100.0, 1000.0, float("inf")])
        m.observe("agent_turn_duration_ms", 250.0)
        assert sample_value(m.registry, "agent_turn_duration_ms_bucket", {"le": "100.0"}) == 0.0
        assert sample_value(m.registry, "agent_turn_duration_ms_bucket", {"le": "1000.0"}) == 1.0


class TestStructlogTraceSink:
    async def test_emit_logs_event_fields(self, capsys) -> None:
        sink = StructlogTraceSink()
        event = make_event()
        await sink.emit(event)
        out = capsys.readouterr().out
        assert "turn_started" in out
        assert "session_id=s1" in out
        assert "trace_id=tr:1" in out

    async def test_emit_never_raises_on_event_types(self, capsys) -> None:
        """所有事件类型都可安全写入（§20：trace sink 失败不阻断业务）。"""
        sink = StructlogTraceSink()
        for event_type in EventType:
            await sink.emit(make_event(event_type=event_type))
        out = capsys.readouterr().out
        assert "results_ready" in out or "turn_failed" in out
