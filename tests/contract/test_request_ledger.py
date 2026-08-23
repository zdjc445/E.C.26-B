"""PostgreSQL Request Ledger contract。"""

from __future__ import annotations

import asyncio

import pytest

from shijiajing_agent.adapters.request_ledger import PostgresRequestLedgerAdapter
from shijiajing_agent.contracts import AgentResponse, AgentStatus

pytestmark = pytest.mark.integration


async def test_postgres_request_ledger_replay_is_idempotent(postgres_dsn: str) -> None:
    ledger = PostgresRequestLedgerAdapter(postgres_dsn)
    await ledger.setup()
    try:
        response = AgentResponse(
            session_id="contract-ledger",
            request_id="r1",
            turn_id="t1",
            trace_id="tr1",
            status=AgentStatus.SUCCESS,
        )
        await ledger.save_response("contract-ledger", "r1", response)
        await ledger.save_response("contract-ledger", "r1", response.model_copy(deep=True))
        assert await ledger.get_response("contract-ledger", "r1") == response
    finally:
        await ledger.close()


async def test_postgres_request_ledger_concurrent_replay_is_idempotent(
    postgres_dsn: str,
) -> None:
    ledger = PostgresRequestLedgerAdapter(postgres_dsn)
    await ledger.setup()
    try:
        response = AgentResponse(
            session_id="contract-ledger-concurrent",
            request_id="r1",
            turn_id="t1",
            trace_id="tr1",
            status=AgentStatus.SUCCESS,
        )
        await asyncio.gather(
            *(
                ledger.save_response(
                    "contract-ledger-concurrent",
                    "r1",
                    response.model_copy(deep=True),
                )
                for _ in range(16)
            )
        )
        assert await ledger.get_response("contract-ledger-concurrent", "r1") == response
    finally:
        await ledger.close()
