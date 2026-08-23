"""追加式持久化事件端口。"""

from __future__ import annotations

from typing import Protocol

from shijiajing_agent.contracts import AgentEventRecord
from shijiajing_agent.ports.lifecycle import ResourceLifecyclePort


class EventStorePort(ResourceLifecyclePort, Protocol):
    async def append(self, event: AgentEventRecord) -> None: ...

    async def list_turn(self, session_id: str, turn_id: str) -> list[AgentEventRecord]: ...
