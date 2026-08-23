"""PostgreSQL Event Store contract。"""

from __future__ import annotations

import pytest

from shijiajing_agent.adapters.event_store import PostgresEventStoreAdapter, stable_event_id
from shijiajing_agent.contracts import AgentEventRecord

pytestmark = pytest.mark.integration


async def test_postgres_event_store_append_is_idempotent(postgres_dsn: str) -> None:
    store = PostgresEventStoreAdapter(postgres_dsn)
    await store.setup()
    try:
        event = AgentEventRecord(
            event_id=stable_event_id("contract-events", "r1", "t1", "supervisor", None, "test", 0),
            session_id="contract-events",
            request_id="r1",
            turn_id="t1",
            trace_id="tr1",
            agent_name="supervisor",
            event_type="test",
            payload={"safe": True},
            occurred_at="2026-08-22T00:00:00+00:00",
        )
        await store.append(event)
        await store.append(event.model_copy(deep=True))
        assert len(await store.list_turn("contract-events", "t1")) == 1
    finally:
        await store.close()
