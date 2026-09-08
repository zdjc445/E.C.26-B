"""记忆服务；commit 只接受 runtime 生成的授权绑定。"""

from __future__ import annotations

from shijiajing_agent.contracts import (
    MemoryDirective,
    MemoryMutation,
    MemoryQuery,
    MemoryRecord,
)
from shijiajing_agent.domain.memory_policy import (
    build_memory_mutation,
    memory_authorization_id,
    validate_directive,
)
from shijiajing_agent.domain.taxonomy import Taxonomy
from shijiajing_agent.errors import CapabilityDeniedError
from shijiajing_agent.ports.memory import MemoryPort


class MemoryService:
    def __init__(self, memory: MemoryPort | None, taxonomy: Taxonomy) -> None:
        self._memory = memory
        self._taxonomy = taxonomy

    async def recall(self, owner_id: str, query: MemoryQuery) -> list[MemoryRecord]:
        if self._memory is None:
            return []
        return await self._memory.recall(owner_id, query)

    def prepare(
        self,
        owner_id: str,
        session_id: str,
        request_id: str,
        directives: list[MemoryDirective],
    ) -> list[MemoryMutation]:
        mutations: list[MemoryMutation] = []
        for index, directive in enumerate(directives):
            try:
                mutations.append(
                    build_memory_mutation(
                        owner_id,
                        session_id,
                        request_id,
                        index,
                        validate_directive(directive, self._taxonomy),
                    )
                )
            except Exception:
                continue
        return mutations

    async def commit(
        self,
        owner_id: str,
        mutations: list[MemoryMutation],
        *,
        interrupt_id: str,
        authorization_id: str,
    ) -> list[MemoryRecord]:
        expected = memory_authorization_id(interrupt_id, mutations)
        if expected != authorization_id:
            raise CapabilityDeniedError("Memory commit 授权与当前 mutations 不匹配")
        if self._memory is None:
            raise RuntimeError("memory_unavailable")
        return await self._memory.commit(owner_id, mutations)


__all__ = ["MemoryService"]
