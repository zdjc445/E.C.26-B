"""跨会话显式记忆端口。"""

from __future__ import annotations

from typing import Protocol

from shijiajing_agent.contracts import MemoryMutation, MemoryQuery, MemoryRecord
from shijiajing_agent.ports.lifecycle import ResourceLifecyclePort


class MemoryPort(ResourceLifecyclePort, Protocol):
    async def recall(self, memory_owner_id: str, query: MemoryQuery) -> list[MemoryRecord]: ...

    async def commit(
        self, memory_owner_id: str, mutations: list[MemoryMutation]
    ) -> list[MemoryRecord]: ...

    async def list_memories(self, memory_owner_id: str) -> list[MemoryRecord]: ...

    async def clear_owner(self, memory_owner_id: str, mutation_id: str) -> None: ...
