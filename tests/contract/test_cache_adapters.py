"""PostgreSQL Versioned Cache contract。"""

from __future__ import annotations

import pytest

from shijiajing_agent.adapters.cache import PostgresVersionedCacheAdapter, canonical_cache_key

pytestmark = pytest.mark.integration


async def test_postgres_cache_round_trip_and_namespace_delete(postgres_dsn: str) -> None:
    cache = PostgresVersionedCacheAdapter(postgres_dsn)
    await cache.setup()
    try:
        key = canonical_cache_key({"b": 2, "a": 1})
        await cache.set("contract-cache", key, {"answer": "ok"}, 60)
        assert await cache.get("contract-cache", key) == {"answer": "ok"}
        await cache.delete_namespace("contract-cache")
        assert await cache.get("contract-cache", key) is None
    finally:
        await cache.close()
