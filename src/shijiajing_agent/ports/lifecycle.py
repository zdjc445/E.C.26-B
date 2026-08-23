"""可由 runtime 管理的外部资源生命周期协议。"""

from __future__ import annotations

from collections.abc import Awaitable
from typing import Protocol, runtime_checkable


@runtime_checkable
class ResourceLifecyclePort(Protocol):
    """支持同步或异步 setup/close 的资源协议。"""

    def setup(self) -> Awaitable[None] | None: ...

    def close(self) -> Awaitable[None] | None: ...
