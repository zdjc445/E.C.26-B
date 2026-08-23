"""可观测性适配器 contract 测试（方案 §20、§21.5 trace sink 不可用）。"""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from shijiajing_agent.adapters.observability import (
    OpenTelemetryTraceSink,
    PrometheusMetrics,
    StructlogTraceSink,
)
from shijiajing_agent.contracts import AgentEvent, EventType, NodeStatus, now_iso


class _OTLPCollectorHandler(BaseHTTPRequestHandler):
    body = b""

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        type(self).body = self.rfile.read(length)
        self.send_response(200)
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        del format, args


class _FailingSpanExporter(SpanExporter):
    def export(self, spans) -> SpanExportResult:
        del spans
        return SpanExportResult.FAILURE


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


class TestOpenTelemetryTraceSink:
    async def test_export_failure_is_reported_to_facade_boundary(self) -> None:
        sink = OpenTelemetryTraceSink(exporter=_FailingSpanExporter())
        await sink.emit(make_event(event_type=EventType.TURN_STARTED, node_name=None))
        with pytest.raises(RuntimeError, match="span export failed"):
            await sink.emit(make_event(event_type=EventType.NODE_COMPLETED))
        sink.close()

    async def test_turn_and_child_spans_are_exported_without_free_text(self) -> None:
        exporter = InMemorySpanExporter()
        sink = OpenTelemetryTraceSink(exporter=exporter)
        await sink.emit(make_event(event_type=EventType.TURN_STARTED, node_name=None))
        await sink.emit(make_event(event_type=EventType.NODE_COMPLETED))
        await sink.emit(make_event(event_type=EventType.RESULTS_READY, node_name=None))
        spans = exporter.get_finished_spans()
        assert [span.name for span in spans] == [
            "shijiajing.node",
            "shijiajing.result",
            "shijiajing.agent",
            "shijiajing.turn",
        ]
        turn = next(span for span in spans if span.name == "shijiajing.turn")
        agent = next(span for span in spans if span.name == "shijiajing.agent")
        node = next(span for span in spans if span.name == "shijiajing.node")
        assert node.parent is not None
        assert agent.parent is not None
        assert agent.parent.span_id == turn.context.span_id
        assert node.parent.span_id == agent.context.span_id
        assert "shijiajing.request_id" in node.attributes
        assert node.attributes["shijiajing.agent_name"] == "supervisor"
        assert "用户文本" not in str(node.attributes)
        sink.close()

    async def test_duplicate_turn_started_is_idempotent(self) -> None:
        exporter = InMemorySpanExporter()
        sink = OpenTelemetryTraceSink(exporter=exporter)
        event = make_event(event_type=EventType.TURN_STARTED, node_name=None)
        await sink.emit(event)
        await sink.emit(event)
        await sink.emit(make_event(event_type=EventType.NODE_COMPLETED))
        await sink.emit(make_event(event_type=EventType.RESULTS_READY, node_name=None))

        spans = exporter.get_finished_spans()
        assert [span.name for span in spans] == [
            "shijiajing.node",
            "shijiajing.result",
            "shijiajing.agent",
            "shijiajing.turn",
        ]
        assert len({span.context.trace_id for span in spans}) == 1
        sink.close()

    async def test_model_nodes_use_model_span(self) -> None:
        exporter = InMemorySpanExporter()
        sink = OpenTelemetryTraceSink(exporter=exporter)
        await sink.emit(make_event(event_type=EventType.TURN_STARTED, node_name=None))
        await sink.emit(
            make_event(
                event_type=EventType.NODE_COMPLETED,
                node_name="parse_intent",
                prompt_version="v1",
                taxonomy_version="taxonomy-v1",
                token_usage={"prompt_tokens": 3, "completion_tokens": 5},
            )
        )
        await sink.emit(make_event(event_type=EventType.RESULTS_READY, node_name=None))
        model = next(
            span for span in exporter.get_finished_spans() if span.name == "shijiajing.model"
        )
        assert model.attributes["shijiajing.prompt_version"] == "v1"
        assert model.attributes["shijiajing.taxonomy_version"] == "taxonomy-v1"
        assert model.attributes["shijiajing.token_usage.prompt_tokens"] == 3
        assert model.attributes["shijiajing.token_usage.completion_tokens"] == 5
        sink.close()

    async def test_trace_id_is_continuous_across_sink_restart(self) -> None:
        first_exporter = InMemorySpanExporter()
        first_sink = OpenTelemetryTraceSink(exporter=first_exporter)
        await first_sink.emit(make_event(event_type=EventType.TURN_STARTED, node_name=None))
        await first_sink.emit(make_event(event_type=EventType.NODE_COMPLETED, node_name="cache"))
        await first_sink.emit(make_event(event_type=EventType.RESULTS_READY, node_name=None))
        first_sink.close()

        second_exporter = InMemorySpanExporter()
        second_sink = OpenTelemetryTraceSink(exporter=second_exporter)
        await second_sink.emit(make_event(event_type=EventType.TURN_STARTED, node_name=None))
        await second_sink.emit(make_event(event_type=EventType.NODE_COMPLETED, node_name="cache"))
        await second_sink.emit(make_event(event_type=EventType.RESULTS_READY, node_name=None))
        second_sink.close()

        first_trace_ids = {span.context.trace_id for span in first_exporter.get_finished_spans()}
        second_trace_ids = {span.context.trace_id for span in second_exporter.get_finished_spans()}
        assert len(first_trace_ids) == 1
        assert second_trace_ids == first_trace_ids

    async def test_component_spans_are_children_of_agent(self) -> None:
        exporter = InMemorySpanExporter()
        sink = OpenTelemetryTraceSink(exporter=exporter)
        await sink.emit(make_event(event_type=EventType.TURN_STARTED, node_name=None))
        await sink.emit(
            make_event(
                event_type=EventType.NODE_COMPLETED,
                node_name="cache",
                cache_hit=True,
            )
        )
        await sink.emit(make_event(event_type=EventType.NODE_COMPLETED, node_name="checkpoint"))
        await sink.emit(make_event(event_type=EventType.NODE_COMPLETED, node_name="request_ledger"))
        await sink.emit(make_event(event_type=EventType.RESULTS_READY, node_name=None))
        spans = exporter.get_finished_spans()
        component_names = {span.name for span in spans}
        assert {
            "shijiajing.cache",
            "shijiajing.checkpoint",
            "shijiajing.request_ledger",
        }.issubset(component_names)
        cache = next(span for span in spans if span.name == "shijiajing.cache")
        agent = next(span for span in spans if span.name == "shijiajing.agent")
        assert cache.parent is not None
        assert cache.parent.span_id == agent.context.span_id
        assert cache.attributes["shijiajing.cache_hit"] is True
        sink.close()

    async def test_otlp_http_exporter_sends_to_real_local_endpoint(self) -> None:
        _OTLPCollectorHandler.body = b""
        server = ThreadingHTTPServer(("127.0.0.1", 0), _OTLPCollectorHandler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            endpoint = f"http://127.0.0.1:{server.server_port}/v1/traces"
            sink = OpenTelemetryTraceSink(exporter=OTLPSpanExporter(endpoint=endpoint))
            await sink.emit(make_event(event_type=EventType.TURN_STARTED, node_name=None))
            await sink.emit(make_event(event_type=EventType.NODE_COMPLETED, node_name="cache"))
            await sink.emit(make_event(event_type=EventType.RESULTS_READY, node_name=None))
            sink.close()
            assert _OTLPCollectorHandler.body
            assert (
                b"\xe7\x94\xa8\xe6\x88\xb7"
                b"\xe6\x96\x87\xe6\x9c\xac" not in _OTLPCollectorHandler.body
            )
        finally:
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()
