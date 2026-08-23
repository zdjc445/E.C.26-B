"""版本感知缓存端口。缓存不是业务正确性来源。"""

from __future__ import annotations

from typing import Any, Protocol

from shijiajing_agent.ports.lifecycle import ResourceLifecyclePort


class VersionedCachePort(ResourceLifecyclePort, Protocol):
    """版本感知缓存及其 runtime 生命周期。"""

    async def get(self, namespace: str, key: str) -> dict[str, Any] | None: ...

    async def set(
        self, namespace: str, key: str, value: dict[str, Any], ttl_seconds: int
    ) -> None: ...

    async def delete_namespace(self, namespace: str) -> None: ...
