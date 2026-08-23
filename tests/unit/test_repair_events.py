"""一致性事件 repair CLI 的 SQLite 端到端测试。"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from shijiajing_agent.adapters.event_store import (
    SQLiteEventStoreAdapter,
    memory_event_attempt,
    stable_event_id,
)
from shijiajing_agent.adapters.memory import SQLiteMemoryAdapter
from shijiajing_agent.adapters.request_ledger import SQLiteRequestLedgerAdapter
from shijiajing_agent.contracts import (
    AgentEventRecord,
    AgentExecutionContext,
    AgentRequest,
    AgentResponse,
    AgentStatus,
    MemoryApplyMode,
    MemoryDirective,
    MemoryOperation,
    now_iso,
)
from shijiajing_agent.domain.memory_policy import build_memory_mutation
from shijiajing_agent.nodes.memory_nodes import make_commit_memory_node
from shijiajing_agent.state import new_state
from shijiajing_agent.tools import repair_events as repair_events_module
from shijiajing_agent.tools.repair_events import main


def _response() -> AgentResponse:
    return AgentResponse(
        session_id="session-1",
        request_id="request-1",
        turn_id="turn-1",
        status=AgentStatus.SUCCESS,
        message="ok",
        trace_id="trace-1",
    )


@pytest.mark.asyncio
async def test_repair_events_rebuilds_request_and_all_memory_events(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ledger_path = tmp_path / "ledger.db"
    memory_path = tmp_path / "memory.db"
    event_path = tmp_path / "events.db"

    ledger = SQLiteRequestLedgerAdapter(str(ledger_path))
    await ledger.setup()
    response = _response()
    await ledger.save_response(response.session_id, response.request_id, response)
    await ledger.close()

    memory = SQLiteMemoryAdapter(str(memory_path))
    await memory.setup()
    mutations = [
        build_memory_mutation(
            "owner-1",
            response.session_id,
            response.request_id,
            index,
            directive,
        )
        for index, directive in enumerate(
            [
                MemoryDirective(
                    operation=MemoryOperation.UPSERT,
                    memory_key="max_price",
                    value=1000,
                    apply_mode=MemoryApplyMode.CONSTRAINT_DEFAULT,
                ),
                MemoryDirective(
                    operation=MemoryOperation.UPSERT,
                    memory_key="min_rating",
                    value=4.5,
                    apply_mode=MemoryApplyMode.CONSTRAINT_DEFAULT,
                ),
            ]
        )
    ]
    await memory.commit("owner-1", mutations)
    await memory.close()

    event_store = SQLiteEventStoreAdapter(str(event_path))
    await event_store.setup()
    await event_store.close()

    assert (
        main(
            [
                "--dsn",
                str(event_path),
                "--ledger-dsn",
                str(ledger_path),
                "--memory-dsn",
                str(memory_path),
                "--dry-run",
            ]
        )
        == 0
    )
    assert "可补建 3 条一致性事件" in capsys.readouterr().out

    assert (
        main(
            [
                "--dsn",
                str(event_path),
                "--ledger-dsn",
                str(ledger_path),
                "--memory-dsn",
                str(memory_path),
                "--apply",
            ]
        )
        == 0
    )
    event_store = SQLiteEventStoreAdapter(str(event_path))
    await event_store.setup()
    events = await event_store.list_turn(response.session_id, response.turn_id)
    await event_store.close()

    assert [event.event_type for event in events] == [
        "request_result_committed",
        "memory_committed",
        "memory_committed",
    ]
    memory_events = [event for event in events if event.event_type == "memory_committed"]
    assert {event.event_id for event in memory_events} == {
        stable_event_id(
            response.session_id,
            response.request_id,
            response.turn_id,
            "memory",
            "commit_memory",
            "memory_committed",
            memory_event_attempt(mutation.mutation_id),
        )
        for mutation in mutations
    }
    assert all(event.trace_id == response.trace_id for event in memory_events)


@pytest.mark.asyncio
async def test_repair_events_accepts_live_memory_event(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ledger_path = tmp_path / "ledger.db"
    memory_path = tmp_path / "memory.db"
    event_path = tmp_path / "events.db"
    response = _response()

    ledger = SQLiteRequestLedgerAdapter(str(ledger_path))
    await ledger.setup()
    await ledger.save_response(response.session_id, response.request_id, response)
    await ledger.close()

    memory = SQLiteMemoryAdapter(str(memory_path))
    await memory.setup()
    mutation = build_memory_mutation(
        "owner-1",
        response.session_id,
        response.request_id,
        0,
        MemoryDirective(
            operation=MemoryOperation.UPSERT,
            memory_key="max_price",
            value=1000,
            apply_mode=MemoryApplyMode.CONSTRAINT_DEFAULT,
        ),
    )
    event_store = SQLiteEventStoreAdapter(str(event_path))
    await event_store.setup()
    state = new_state(
        schema_version="1.1",
        session_id=response.session_id,
        request_id=response.request_id,
        turn_id=response.turn_id,
        trace_id=response.trace_id,
        current_request=AgentRequest(
            session_id=response.session_id,
            request_id=response.request_id,
            text="记住预算",
        ),
    )
    state["execution_context"] = AgentExecutionContext(
        memory_enabled=True,
        memory_owner_id="owner-1",
    )
    state["pending_memory_mutations"] = [mutation]
    deps = SimpleNamespace(
        memory=memory,
        event_store=event_store,
        metrics=SimpleNamespace(inc=lambda *args, **kwargs: None),
    )
    await make_commit_memory_node(deps)(state)
    await event_store.close()
    await memory.close()

    assert (
        main(
            [
                "--dsn",
                str(event_path),
                "--ledger-dsn",
                str(ledger_path),
                "--memory-dsn",
                str(memory_path),
                "--dry-run",
            ]
        )
        == 0
    )
    assert "可补建 1 条一致性事件" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_repair_events_does_not_fabricate_memory_trace_ids(tmp_path: Path) -> None:
    memory_path = tmp_path / "memory.db"
    event_path = tmp_path / "events.db"
    memory = SQLiteMemoryAdapter(str(memory_path))
    await memory.setup()
    mutation = build_memory_mutation(
        "owner-1",
        "session-1",
        "request-without-ledger",
        0,
        MemoryDirective(
            operation=MemoryOperation.UPSERT,
            memory_key="max_price",
            value=1000,
            apply_mode=MemoryApplyMode.CONSTRAINT_DEFAULT,
        ),
    )
    await memory.commit("owner-1", [mutation])
    await memory.close()
    event_store = SQLiteEventStoreAdapter(str(event_path))
    await event_store.setup()
    await event_store.close()

    assert (
        main(
            [
                "--dsn",
                str(event_path),
                "--memory-dsn",
                str(memory_path),
                "--apply",
            ]
        )
        == 0
    )
    import sqlite3

    with sqlite3.connect(event_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM agent_event").fetchone()[0] == 0


@pytest.mark.asyncio
async def test_repair_events_stops_on_same_id_content_conflict(tmp_path: Path) -> None:
    ledger_path = tmp_path / "ledger.db"
    event_path = tmp_path / "events.db"
    response = _response()
    ledger = SQLiteRequestLedgerAdapter(str(ledger_path))
    await ledger.setup()
    await ledger.save_response(response.session_id, response.request_id, response)
    await ledger.close()

    event_id = stable_event_id(
        response.session_id,
        response.request_id,
        response.turn_id,
        "supervisor",
        None,
        "request_result_committed",
        0,
    )
    event_store = SQLiteEventStoreAdapter(str(event_path))
    await event_store.setup()
    await event_store.append(
        AgentEventRecord(
            event_id=event_id,
            session_id=response.session_id,
            request_id=response.request_id,
            turn_id=response.turn_id,
            trace_id=response.trace_id,
            agent_name="supervisor",
            node_name=None,
            event_type="request_result_committed",
            status="failed",
            payload={"response_hash": "wrong"},
            occurred_at=now_iso(),
        )
    )
    await event_store.close()

    assert (
        main(
            [
                "--dsn",
                str(event_path),
                "--ledger-dsn",
                str(ledger_path),
                "--dry-run",
            ]
        )
        == 2
    )


@pytest.mark.asyncio
async def test_repair_events_closes_store_when_setup_fails(monkeypatch) -> None:
    class FailingStore:
        close_calls = 0

        async def setup(self) -> None:
            raise RuntimeError("simulated setup failure")

        async def append(self, event: AgentEventRecord) -> None:
            del event

        async def close(self) -> None:
            FailingStore.close_calls += 1

    store = FailingStore()
    monkeypatch.setattr(
        repair_events_module,
        "make_event_store_adapter",
        lambda backend, dsn: store,
    )

    with pytest.raises(RuntimeError, match="simulated setup failure"):
        await repair_events_module._append_events("sqlite", "unused", [])

    assert FailingStore.close_calls == 1
