"""版本感知缓存键和故障降级辅助函数。"""

from __future__ import annotations

from typing import Any, cast

from shijiajing_agent.adapters.cache import canonical_cache_key
from shijiajing_agent.ports.cache import VersionedCachePort
from shijiajing_agent.ports.observability import MetricsPort


def _record_cache_failure(metrics: MetricsPort | None, operation: str) -> None:
    """缓存故障只增加指标，指标自身故障也不能影响业务。"""
    if metrics is None:
        return
    try:
        metrics.inc("cache_failure_total", {"operation": operation})
    except Exception:
        return


def versioned_key(payload: Any, versions: dict[str, str | None]) -> str:
    return canonical_cache_key({"payload": payload, "versions": versions})


async def safe_get(
    cache: VersionedCachePort | None,
    namespace: str,
    key: str,
    *,
    metrics: MetricsPort | None = None,
) -> dict[str, Any] | None:
    if cache is None:
        return None
    try:
        value: Any = await cache.get(namespace, key)
        return cast(dict[str, Any], value) if isinstance(value, dict) else None
    except Exception:
        _record_cache_failure(metrics, "get")
        return None


async def safe_set(
    cache: VersionedCachePort | None,
    namespace: str,
    key: str,
    value: dict[str, Any],
    ttl_seconds: int,
    *,
    metrics: MetricsPort | None = None,
) -> None:
    if cache is None:
        return
    try:
        await cache.set(namespace, key, value, ttl_seconds)
    except Exception:
        _record_cache_failure(metrics, "set")
        return


async def safe_delete_namespace(
    cache: VersionedCachePort | None,
    namespace: str,
    *,
    metrics: MetricsPort | None = None,
) -> None:
    """运维清理失败按 cache 故障处理，不向业务调用方传播。"""
    if cache is None:
        return
    try:
        await cache.delete_namespace(namespace)
    except Exception:
        _record_cache_failure(metrics, "delete")
        return
