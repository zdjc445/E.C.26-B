"""可观测性适配器（方案 §20）。

- ``StructlogTraceSink``：每个 AgentEvent 一条结构化日志（structlog）。
- ``PrometheusMetrics``：prometheus-client Counter / Histogram，按名称 + 标签集动态注册。

失败语义（§20）：trace sink 与指标失败均不阻断业务结果；facade 对 trace 失败
额外累加 ``trace_sink_failure_total`` 本地错误计数。Checkpoint 失败阻断成功提交，
见 ``adapters.checkpoint``。
"""

from __future__ import annotations

import structlog
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


class StructlogTraceSink:
    """每个 AgentEvent 一条结构化日志。失败不阻断业务（facade 兜底计数）。"""

    def __init__(self, logger_name: str = "shijiajing.trace") -> None:
        self._logger = structlog.get_logger(logger_name)

    async def emit(self, event: AgentEvent) -> None:
        self._logger.info(event.event_type.value, **event.model_dump())


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
    """按配置构建 trace sink。当前仅 structlog 后端。"""
    del settings  # structlog 为默认与唯一后端；TRACE_BACKEND 预留其他实现
    return StructlogTraceSink()


def make_metrics(settings: Settings) -> MetricsPort:
    """按配置构建指标输出。当前仅 prometheus-client 后端。"""
    del settings
    return PrometheusMetrics()
