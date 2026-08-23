"""PostgreSQL Memory contract。"""

from __future__ import annotations

import asyncio

import pytest

from shijiajing_agent.adapters.memory import PostgresMemoryAdapter
from shijiajing_agent.contracts import (
    MemoryApplyMode,
    MemoryDirective,
    MemoryOperation,
    MemoryQuery,
)
from shijiajing_agent.domain.memory_policy import build_memory_mutation

pytestmark = pytest.mark.integration


async def test_postgres_memory_owner_isolation_and_replay(postgres_dsn: str) -> None:
    memory = PostgresMemoryAdapter(postgres_dsn)
    await memory.setup()
    try:
        directive = MemoryDirective(
            operation=MemoryOperation.UPSERT,
            memory_key="max_price",
            value=1000,
            apply_mode=MemoryApplyMode.CONSTRAINT_DEFAULT,
        )
        mutation = build_memory_mutation("contract-owner", "s1", "r1", 0, directive)
        assert len(await memory.commit("contract-owner", [mutation, mutation])) == 1
        query = MemoryQuery(scope_keys=["global"], limit=20)
        assert len(await memory.recall("contract-owner", query)) == 1
        assert await memory.recall("other-owner", query) == []
    finally:
        await memory.close()


async def test_postgres_memory_concurrent_replay_is_idempotent(postgres_dsn: str) -> None:
    memory = PostgresMemoryAdapter(postgres_dsn)
    await memory.setup()
    try:
        mutation = build_memory_mutation(
            "concurrent-owner",
            "s1",
            "r1",
            0,
            MemoryDirective(
                operation=MemoryOperation.UPSERT,
                memory_key="max_price",
                value=1000,
                apply_mode=MemoryApplyMode.CONSTRAINT_DEFAULT,
            ),
        )
        results = await asyncio.gather(
            *(memory.commit("concurrent-owner", [mutation]) for _ in range(16))
        )
        assert sum(len(batch) for batch in results) == 1
        records = await memory.recall(
            "concurrent-owner", MemoryQuery(scope_keys=["global"], limit=20)
        )
        assert len(records) == 1
    finally:
        await memory.close()
