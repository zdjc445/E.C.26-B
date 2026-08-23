"""Event Store turn 还原工具测试。"""

from __future__ import annotations

import asyncio
import json

import pytest

from shijiajing_agent.adapters.event_store import SQLiteEventStoreAdapter, stable_event_id
from shijiajing_agent.contracts import AgentEventRecord
from shijiajing_agent.tools import reconstruct_turn as reconstruct_turn_module
from shijiajing_agent.tools.reconstruct_turn import main, reconstruct_turn


def make_event(
    event_type: str,
    *,
    event_id: str | None = None,
    occurred_at: str,
    request_id: str = "r1",
    trace_id: str = "trace-1",
    agent_name: str = "supervisor",
    node_name: str | None = "parse_intent",
    payload: dict[str, object] | None = None,
) -> AgentEventRecord:
    return AgentEventRecord(
        event_id=event_id
        or stable_event_id("s1", request_id, "t1", agent_name, node_name, event_type, 0),
        session_id="s1",
        request_id=request_id,
        turn_id="t1",
        trace_id=trace_id,
        agent_name=agent_name,
        node_name=node_name,
        event_type=event_type,
        status="success",
        payload=payload or {},
        occurred_at=occurred_at,
    )


def test_reconstruct_turn_orders_events_and_collects_versions() -> None:
    result = reconstruct_turn(
        [
            make_event("agent_completed", occurred_at="2026-08-22T00:00:02+00:00"),
            make_event(
                "agent_started",
                occurred_at="2026-08-22T00:00:00+00:00",
                node_name=None,
                payload={"prompt_version": "prompt-v1", "taxonomy_version": "taxonomy-v1"},
            ),
            make_event(
                "node_completed",
                occurred_at="2026-08-22T00:00:01+00:00",
                payload={"prompt_version": "prompt-v1", "fusion_version": "weighted-v1"},
            ),
            make_event(
                "agent_failed",
                occurred_at="2026-08-22T00:00:03+00:00",
                agent_name="memory",
                node_name="commit_memory",
            ),
        ]
    )

    assert result.event_types == (
        "agent_started",
        "node_completed",
        "agent_completed",
        "agent_failed",
    )
    assert result.node_names == ("parse_intent", "commit_memory")
    assert result.versions == {
        "prompt_version": ("prompt-v1",),
        "taxonomy_version": ("taxonomy-v1",),
        "fusion_version": ("weighted-v1",),
    }
    assert result.terminal_event_type == "agent_completed"
    assert result.trace_id == "trace-1"


def test_reconstruct_turn_rejects_mixed_identity() -> None:
    with pytest.raises(ValueError, match="标识不一致"):
        reconstruct_turn(
            [
                make_event("agent_started", occurred_at="2026-08-22T00:00:00+00:00"),
                make_event(
                    "node_completed",
                    occurred_at="2026-08-22T00:00:01+00:00",
                    trace_id="trace-2",
                ),
            ]
        )


def test_reconstruct_turn_cli_reads_sqlite_without_writing(tmp_path, capsys) -> None:
    dsn = str(tmp_path / "events.db")
    store = SQLiteEventStoreAdapter(dsn)

    async def seed() -> None:
        await store.setup()
        await store.append(
            make_event("agent_started", occurred_at="2026-08-22T00:00:00+00:00", node_name=None)
        )
        await store.append(
            make_event("agent_completed", occurred_at="2026-08-22T00:00:01+00:00", node_name=None)
        )
        await store.close()

    asyncio.run(seed())
    before = (tmp_path / "events.db").stat().st_size
    assert main(["--dsn", dsn, "--session-id", "s1", "--turn-id", "t1", "--json"]) == 0
    after = (tmp_path / "events.db").stat().st_size
    output = json.loads(capsys.readouterr().out)
    assert output["event_count"] == 2
    assert output["trace_id"] == "trace-1"
    assert before == after


def test_reconstruct_turn_closes_store_when_setup_fails(monkeypatch) -> None:
    class FailingStore:
        close_calls = 0

        async def setup(self) -> None:
            raise RuntimeError("simulated setup failure")

        async def close(self) -> None:
            FailingStore.close_calls += 1

    store = FailingStore()
    monkeypatch.setattr(
        reconstruct_turn_module,
        "make_event_store_adapter",
        lambda backend, dsn: store,
    )

    with pytest.raises(RuntimeError, match="simulated setup failure"):
        asyncio.run(
            reconstruct_turn_module._load_turn(
                backend="sqlite",
                dsn="unused",
                session_id="s1",
                turn_id="t1",
                request_id=None,
            )
        )

    assert FailingStore.close_calls == 1
