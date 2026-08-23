"""PostgreSQL 连接池参数传递契约。"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from shijiajing_agent.adapters.cache import PostgresVersionedCacheAdapter
from shijiajing_agent.adapters.checkpoint import PostgresCheckpointAdapter
from shijiajing_agent.adapters.event_store import PostgresEventStoreAdapter
from shijiajing_agent.adapters.memory import PostgresMemoryAdapter
from shijiajing_agent.adapters.request_ledger import PostgresRequestLedgerAdapter


@pytest.mark.parametrize(
    "adapter_type",
    (
        PostgresCheckpointAdapter,
        PostgresRequestLedgerAdapter,
        PostgresMemoryAdapter,
        PostgresVersionedCacheAdapter,
        PostgresEventStoreAdapter,
    ),
)
def test_postgres_adapters_forward_pool_parameters(adapter_type: type[object]) -> None:
    with patch("psycopg_pool.AsyncConnectionPool") as pool:
        adapter_type(
            "postgresql://user:password@localhost/db",
            min_size=2,
            max_size=8,
            timeout_seconds=12.5,
        )

    pool.assert_called_once_with(
        "postgresql://user:password@localhost/db",
        min_size=2,
        max_size=8,
        timeout=12.5,
        open=False,
    )
