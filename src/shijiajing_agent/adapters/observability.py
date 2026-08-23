"""可观测性适配器（方案 §20）。

- ``StructlogTraceSink``：每个 AgentEvent 一条结构化日志（structlog）。
- ``PrometheusMetrics``：prometheus-client Counter / Histogram，按名称 + 标签集动态注册。

失败语义（§20）：trace sink 与指标失败均不阻断业务结果；facade 对 trace 失败
额外累加 ``trace_sink_failure_total`` 本地错误计数。Checkpoint 失败阻断成功提交，
见 ``adapters.checkpoint``。
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version

import structlog
from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import (
    SimpleSpanProcessor,
    SpanExporter,
    SpanExportResult,
)
from opentelemetry.trace import NonRecordingSpan, Span, SpanContext, Status, StatusCode, TraceFlags
from prometheus_client import CollectorRegistry, Counter, Histogram

from shijiajing_agent.config import Settings
from shijiajing_agent.contracts import AgentEvent
from shijiajing_agent.ports.observability import MetricsPort, TraceSinkPort

# 时长（毫秒）观测默认桶：覆盖节点到整轮 turn 的量级
_DEFAULT_DURATION_BUCKETS_MS = [
    1,
    5,
    10,
    25,
    50,
    100,
    250,
    500,
    1000,
    2500,
    5000,
    10000,
    30000,
    60000,
    float("inf"),
]

_MODEL_NODES = frozenset(
    {
        "recognize_image",
        "parse_intent",
        "parse_intent_resume",
        "rewrite_query",
        "generate_explanation",
    }
)
_RETRIEVAL_NODES = frozenset(
    {"retrieve_candidates", "relax_recognition_constraints", "normalize_candidates"}
)
_MEMORY_NODES = frozenset(
    {"recall_memory", "prepare_memory_mutations", "commit_memory", "append_turn_summary"}
)
_CACHE_NODES = frozenset({"cache"})
_CHECKPOINT_NODES = frozenset({"checkpoint"})
_REQUEST_LEDGER_NODES = frozenset({"request_ledger"})


@dataclass
class _TurnSpan:
    turn: Span
    turn_context: Context
    agent: Span
    agent_context: Context


class _TrackingSpanExporter(SpanExporter):
    """记录 OTLP exporter 的 FAILURE 结果，避免 SDK 只写日志而丢失失败语义。"""

    def __init__(self, delegate: SpanExporter) -> None:
        self._delegate = delegate
        self.failure_count = 0

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        try:
            result = self._delegate.export(spans)
        except Exception:
            self.failure_count += 1
            raise
        if result is SpanExportResult.FAILURE:
            self.failure_count += 1
        return result

    def shutdown(self) -> None:
        self._delegate.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self._delegate.force_flush(timeout_millis)


class StructlogTraceSink:
    """每个 AgentEvent 一条结构化日志。失败不阻断业务（facade 兜底计数）。"""

    def __init__(self, logger_name: str = "shijiajing.trace") -> None:
        self._logger = structlog.get_logger(logger_name)

    def setup(self) -> None:
        """structlog 不持有外部连接；保留统一 runtime 生命周期入口。"""

    def close(self) -> None:
        """structlog sink 无需释放外部资源。"""

    async def emit(self, event: AgentEvent) -> None:
        self._logger.info(event.event_type.value, **event.model_dump())


class OpenTelemetryTraceSink:
    """脱敏的 OpenTelemetry span sink。

    TURN_STARTED 创建 turn 根 span；其余事件创建以该 turn 为父级的短 span。
    ``exporter`` 可由 contract 测试注入；生产装配可使用 OTLP exporter。
    """

    def __init__(
        self,
        *,
        exporter: SpanExporter | None = None,
        service_name: str = "shijiajing-agent",
    ) -> None:
        resource_attributes: dict[str, str] = {"service.name": service_name}
        try:
            resource_attributes["service.version"] = version("shijiajing-agent")
        except PackageNotFoundError:
            pass
        provider = TracerProvider(resource=Resource.create(resource_attributes))
        self._exporter: _TrackingSpanExporter | None = None
        if exporter is not None:
            self._exporter = _TrackingSpanExporter(exporter)
            provider.add_span_processor(SimpleSpanProcessor(self._exporter))
        self.provider = provider
        self._tracer = provider.get_tracer("shijiajing-agent")
        self._turn_spans: dict[tuple[str, str], _TurnSpan] = {}
        self._closed = False

    def setup(self) -> None:
        """TracerProvider 在构造时完成 setup；保留统一 runtime 生命周期入口。"""

    async def emit(self, event: AgentEvent) -> None:
        key = (event.session_id, event.turn_id)
        if event.event_type.value == "turn_started":
            if key in self._turn_spans:
                # replay/重试可能重复投影 turn_started；保持同一棵 root span，避免悬挂旧树。
                return
            turn = self._tracer.start_span(
                "shijiajing.turn", context=_trace_parent_context(event.trace_id)
            )
            turn.set_attributes(_span_attributes(event))
            turn_context = trace.set_span_in_context(turn)
            agent = self._tracer.start_span("shijiajing.agent", context=turn_context)
            agent.set_attributes(_span_attributes(event))
            self._turn_spans[key] = _TurnSpan(
                turn=turn,
                turn_context=turn_context,
                agent=agent,
                agent_context=trace.set_span_in_context(agent),
            )
            return

        failures_before = self._exporter.failure_count if self._exporter is not None else 0
        parent = self._turn_spans.get(key)
        context = (
            parent.agent_context if parent is not None else _trace_parent_context(event.trace_id)
        )
        name = _span_name(event)
        with self._tracer.start_as_current_span(name, context=context) as span:
            span.set_attributes(_span_attributes(event))
            if event.error_code is not None or event.event_type.value == "turn_failed":
                span.set_status(Status(StatusCode.ERROR, event.error_code or "turn_failed"))

        if event.event_type.value in {"results_ready", "turn_failed"} and parent is not None:
            parent.agent.set_attributes(_span_attributes(event))
            parent.turn.set_attributes(_span_attributes(event))
            if event.event_type.value == "turn_failed":
                failure = Status(StatusCode.ERROR, event.error_code or "turn_failed")
                parent.agent.set_status(failure)
                parent.turn.set_status(failure)
            parent.agent.end()
            parent.turn.end()
            self._turn_spans.pop(key, None)

        if self._exporter is not None and self._exporter.failure_count > failures_before:
            raise RuntimeError("OpenTelemetry span export failed")

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for parent in self._turn_spans.values():
            parent.agent.end()
            parent.turn.end()
        self._turn_spans.clear()
        self.provider.shutdown()


def _span_name(event: AgentEvent) -> str:
    if event.node_name in _CACHE_NODES:
        return "shijiajing.cache"
    if event.node_name in _CHECKPOINT_NODES:
        return "shijiajing.checkpoint"
    if event.node_name in _REQUEST_LEDGER_NODES:
        return "shijiajing.request_ledger"
    if event.node_name in _MODEL_NODES:
        return "shijiajing.model"
    if event.node_name in _RETRIEVAL_NODES:
        return "shijiajing.retrieval"
    if event.node_name in _MEMORY_NODES:
        return "shijiajing.memory"
    return "shijiajing.node" if event.node_name else "shijiajing.result"


def _trace_parent_context(trace_id: str) -> Context:
    """把业务 trace_id 映射为稳定的 128-bit OTLP Trace ID。

    业务标识当前允许带前缀且长度不固定，因此使用 SHA-256 派生合法的 128-bit
    Trace ID；相同业务 trace_id 在进程重启后仍落入同一条 OTLP Trace。
    """
    digest = hashlib.sha256(trace_id.encode("utf-8")).digest()
    otel_trace_id = int.from_bytes(digest[:16], byteorder="big") or 1
    otel_parent_span_id = int.from_bytes(digest[16:24], byteorder="big") or 1
    parent = SpanContext(
        trace_id=otel_trace_id,
        span_id=otel_parent_span_id,
        is_remote=False,
        trace_flags=TraceFlags(1),
    )
    return trace.set_span_in_context(NonRecordingSpan(parent))


def _span_attributes(event: AgentEvent) -> dict[str, str | int | float | bool]:
    """只投影 ID、版本/模型元数据、哈希、计数和错误码，不投影自由文本。"""
    attrs: dict[str, str | int | float | bool] = {
        "shijiajing.session_id": event.session_id,
        "shijiajing.request_id": event.request_id,
        "shijiajing.turn_id": event.turn_id,
        "shijiajing.trace_id": event.trace_id,
        "shijiajing.event_type": event.event_type.value,
        "shijiajing.agent_name": "supervisor",
    }
    for key, value in (
        ("shijiajing.node_name", event.node_name),
        ("shijiajing.status", event.status.value if event.status is not None else None),
        ("shijiajing.provider", event.provider),
        ("shijiajing.model", event.model),
        ("shijiajing.agent_name", event.agent_name or "supervisor"),
        ("shijiajing.prompt_version", event.prompt_version),
        ("shijiajing.taxonomy_version", event.taxonomy_version),
        ("shijiajing.retrieval_index_version", event.retrieval_index_version),
        ("shijiajing.fusion_version", event.fusion_version),
        ("shijiajing.rerank_version", event.rerank_version),
        ("shijiajing.interrupt_kind", event.interrupt_kind),
        ("shijiajing.checkpoint_migration", event.checkpoint_migration),
        ("shijiajing.input_hash", event.input_hash),
        ("shijiajing.output_hash", event.output_hash),
        ("shijiajing.error_code", event.error_code),
        ("shijiajing.resumed_node", event.resumed_node),
    ):
        if value is not None:
            attrs[key] = value
    for key, value in (
        ("shijiajing.duration_ms", event.duration_ms),
        ("shijiajing.retry_count", event.retry_count),
        ("shijiajing.candidate_count_in", event.candidate_count_in),
        ("shijiajing.candidate_count_out", event.candidate_count_out),
        ("shijiajing.memory_operation_count", event.memory_operation_count),
    ):
        if value is not None:
            attrs[key] = value
    if event.fallback_used is not None:
        attrs["shijiajing.fallback_used"] = event.fallback_used
    if event.resumed is not None:
        attrs["shijiajing.resumed"] = event.resumed
    if event.cache_hit is not None:
        attrs["shijiajing.cache_hit"] = event.cache_hit
    if event.token_usage is not None:
        for name, value in event.token_usage.items():
            attrs[f"shijiajing.token_usage.{name}"] = value
    return attrs


def span_attributes(event: AgentEvent) -> dict[str, str | int | float | bool]:
    """返回脱敏的结构化 span 属性，供独立验收器复用。"""
    return _span_attributes(event)


class PrometheusMetrics:
    """prometheus-client 实现。同一 (名称, 标签集) 复用同一指标对象。

    默认使用独立 CollectorRegistry，避免进程内重复注册冲突；需要对外暴露时
    传入共享 registry（如 ``prometheus_client.REGISTRY``）并接入 scrape 端点。
    """

    def __init__(
        self,
        *,
        registry: CollectorRegistry | None = None,
        duration_buckets_ms: list[float] | None = None,
    ) -> None:
        self.registry = registry or CollectorRegistry()
        self._buckets = duration_buckets_ms or list(_DEFAULT_DURATION_BUCKETS_MS)
        self._counters: dict[tuple[str, frozenset[str]], Counter] = {}
        self._histograms: dict[tuple[str, frozenset[str]], Histogram] = {}

    # ------------------------------------------------------------------
    def inc(self, name: str, labels: dict[str, str] | None = None, value: float = 1.0) -> None:
        labels = labels or {}
        counter = self._counter_for(name, labels)
        (counter.labels(**labels) if labels else counter).inc(value)

    def observe(self, name: str, value: float, labels: dict[str, str] | None = None) -> None:
        labels = labels or {}
        histogram = self._histogram_for(name, labels)
        (histogram.labels(**labels) if labels else histogram).observe(value)

    # ------------------------------------------------------------------
    def _counter_for(self, name: str, labels: dict[str, str]) -> Counter:
        key = (name, frozenset(labels))
        counter = self._counters.get(key)
        if counter is None:
            counter = Counter(
                name,
                f"shijiajing metric: {name}",
                labelnames=sorted(labels),
                registry=self.registry,
            )
            self._counters[key] = counter
        return counter

    def _histogram_for(self, name: str, labels: dict[str, str]) -> Histogram:
        key = (name, frozenset(labels))
        histogram = self._histograms.get(key)
        if histogram is None:
            histogram = Histogram(
                name,
                f"shijiajing metric: {name}",
                labelnames=sorted(labels),
                buckets=self._buckets,
                registry=self.registry,
            )
            self._histograms[key] = histogram
        return histogram


def make_trace_sink(settings: Settings) -> TraceSinkPort:
    """按配置构建 structlog 或 OpenTelemetry trace sink。"""
    if settings.trace_backend == "opentelemetry":
        exporter: SpanExporter | None = None
        if settings.trace_dsn:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

            exporter = OTLPSpanExporter(endpoint=settings.trace_dsn)
        return OpenTelemetryTraceSink(exporter=exporter)
    return StructlogTraceSink()


def make_metrics(settings: Settings) -> MetricsPort:
    """按配置构建指标输出。当前仅 prometheus-client 后端。"""
    del settings
    return PrometheusMetrics()
