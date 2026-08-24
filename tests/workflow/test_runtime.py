"""生产 runtime 资源生命周期和跨 runtime 重启幂等回归。"""

from __future__ import annotations

import sqlite3
from typing import Any

import pytest

from shijiajing_agent.adapters.checkpoint import SQLiteCheckpointAdapter
from shijiajing_agent.adapters.event_store import SQLiteEventStoreAdapter
from shijiajing_agent.adapters.memory import SQLiteMemoryAdapter
from shijiajing_agent.contracts import (
    AgentExecutionContext,
    AgentRequest,
    AgentResume,
    IntentPatch,
    MemoryApplyMode,
    MemoryDirective,
    MemoryOperation,
)
from shijiajing_agent.runtime import open_agent_runtime
from shijiajing_agent.tools.backup_sqlite import main as backup_sqlite_main

from .conftest import (
    FakeRetrieval,
    FakeVisionModel,
    make_deps,
    two_candidate_result,
)
from .conftest import WorkflowSettings as Settings


class _ClosableTrace:
    def __init__(self, events: list[str] | None = None) -> None:
        self.close_calls = 0
        self._events = events

    async def setup(self) -> None:
        return None

    async def emit(self, event: Any) -> None:
        del event

    async def close(self) -> None:
        self.close_calls += 1
        if self._events is not None:
            self._events.append("trace")


class _ClosableVision(FakeVisionModel):
    def __init__(self, events: list[str]) -> None:
        super().__init__()
        self._events = events
        self.close_calls = 0

    async def close(self) -> None:
        self.close_calls += 1
        self._events.append("vision")


class _ClosableRetrieval(FakeRetrieval):
    def __init__(self, events: list[str]) -> None:
        super().__init__()
        self._events = events
        self.close_calls = 0

    async def close(self) -> None:
        self.close_calls += 1
        self._events.append("retrieval")


@pytest.mark.asyncio
async def test_native_runtime_reopens_and_reuses_request_ledger(
    taxonomy: Any, tmp_path: Any
) -> None:
    settings = Settings(
        graph_persistence_mode="native",
        checkpoint_backend="sqlite",
        checkpoint_dsn=str(tmp_path / "checkpoint.db"),
        request_ledger_backend="sqlite",
        request_ledger_dsn=str(tmp_path / "ledger.db"),
    )
    created_fakes: list[dict[str, Any]] = []

    def deps_factory(_: Settings) -> Any:
        retrieval = FakeRetrieval()
        retrieval.sequence = [two_candidate_result()]
        deps, fakes = make_deps(taxonomy, settings, retrieval=retrieval)
        deps.checkpoint = SQLiteCheckpointAdapter(str(settings.checkpoint_dsn))
        created_fakes.append(fakes)
        return deps

    request = AgentRequest(session_id="runtime-restart", request_id="r1", text="索尼耳机")
    context = AgentExecutionContext()

    async with open_agent_runtime(settings, deps_factory=deps_factory) as facade:
        with sqlite3.connect(settings.checkpoint_dsn) as connection:
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
        assert "agent_resume_claim" in tables
        first = await facade.start(request, context)

    assert first.response is not None
    assert len(created_fakes) == 1
    assert created_fakes[0]["retrieval"].calls == 1

    async with open_agent_runtime(settings, deps_factory=deps_factory) as facade:
        second = await facade.start(request, context)

    assert second.response is not None
    assert second.response.model_dump(mode="json") == first.response.model_dump(mode="json")
    assert len(created_fakes) == 2
    assert created_fakes[1]["retrieval"].calls == 0


@pytest.mark.asyncio
async def test_native_runtime_reopens_active_interrupt_and_resumes(
    taxonomy: Any, tmp_path: Any
) -> None:
    """进程重开后从 SQLite native checkpoint 恢复 active interrupt。"""
    settings = Settings(
        graph_persistence_mode="native",
        checkpoint_backend="sqlite",
        checkpoint_dsn=str(tmp_path / "checkpoint-hitl.db"),
        request_ledger_backend="sqlite",
        request_ledger_dsn=str(tmp_path / "ledger-hitl.db"),
        hitl_enabled=True,
    )

    def deps_factory(_: Settings) -> Any:
        retrieval = FakeRetrieval()
        retrieval.sequence = [two_candidate_result()]
        deps, _ = make_deps(taxonomy, settings, retrieval=retrieval)
        deps.checkpoint = SQLiteCheckpointAdapter(str(settings.checkpoint_dsn))
        return deps

    request = AgentRequest(session_id="runtime-hitl-restart", request_id="r1", text="帮我比个价")
    context = AgentExecutionContext()
    async with open_agent_runtime(settings, deps_factory=deps_factory) as facade:
        first = await facade.start(request, context)

    assert first.interrupt is not None
    assert first.interrupt.kind.value == "clarification"

    async with open_agent_runtime(settings, deps_factory=deps_factory) as facade:
        replayed = await facade.start(request, context)
        assert replayed.interrupt is not None
        assert replayed.interrupt.model_dump(mode="json") == first.interrupt.model_dump(mode="json")
        resumed = await facade.resume(
            request.session_id,
            AgentResume(
                interrupt_id=first.interrupt.interrupt_id,
                value={"action": "answer", "text": "索尼耳机"},
            ),
            context,
        )

    assert resumed.response is not None
    assert resumed.interrupt is None


@pytest.mark.asyncio
async def test_sqlite_backup_restore_preserves_native_interrupt_and_resources(
    taxonomy: Any, tmp_path: Any
) -> None:
    """备份四个 SQLite 资源后，重开 runtime 仍可恢复 active interrupt。"""
    source_dir = tmp_path / "source"
    backup_dir = tmp_path / "backup"
    recovered_dir = tmp_path / "recovered"
    source_dir.mkdir()
    source_settings = Settings(
        graph_persistence_mode="native",
        checkpoint_backend="sqlite",
        checkpoint_dsn=str(source_dir / "checkpoint.db"),
        request_ledger_backend="sqlite",
        request_ledger_dsn=str(source_dir / "ledger.db"),
        memory_enabled=True,
        memory_backend="sqlite",
        memory_dsn=str(source_dir / "memory.db"),
        cache_backend="sqlite",
        cache_dsn=str(source_dir / "cache.db"),
        event_store_backend="sqlite",
        event_store_dsn=str(source_dir / "events.db"),
        hitl_enabled=True,
    )
    request = AgentRequest(session_id="sqlite-backup-hitl", request_id="r1", text="找耳机")
    context = AgentExecutionContext(memory_owner_id="owner-a", memory_enabled=True)
    created_fakes: list[dict[str, Any]] = []

    def deps_factory(runtime_settings: Settings) -> Any:
        retrieval = FakeRetrieval()
        retrieval.sequence = [two_candidate_result()]
        deps, fakes = make_deps(taxonomy, runtime_settings, retrieval=retrieval)
        fakes["intent"].results = [
            IntentPatch(
                category_id="headphone",
                memory_directives=[
                    MemoryDirective(
                        operation=MemoryOperation.UPSERT,
                        memory_key="max_price",
                        value=1000,
                        apply_mode=MemoryApplyMode.CONSTRAINT_DEFAULT,
                    )
                ],
            )
        ]
        deps.checkpoint = SQLiteCheckpointAdapter(str(runtime_settings.checkpoint_dsn))
        created_fakes.append(fakes)
        return deps

    async with open_agent_runtime(source_settings, deps_factory=deps_factory) as facade:
        first = await facade.start(request, context)
    assert first.interrupt is not None
    assert first.interrupt.kind.value == "memory_confirmation"

    resource_paths = {
        "checkpoint": source_settings.checkpoint_dsn,
        "ledger": source_settings.request_ledger_dsn,
        "memory": source_settings.memory_dsn,
        "cache": source_settings.cache_dsn,
        "events": source_settings.event_store_dsn,
    }
    recovered_paths: dict[str, str] = {}
    for name, source in resource_paths.items():
        assert source is not None
        backup = backup_dir / f"{name}.db"
        recovered = recovered_dir / f"{name}.db"
        assert (
            backup_sqlite_main(
                [
                    "--mode",
                    "backup",
                    "--source-dsn",
                    source,
                    "--target-dsn",
                    str(backup),
                ]
            )
            == 0
        )
        assert (
            backup_sqlite_main(
                [
                    "--mode",
                    "restore",
                    "--source-dsn",
                    str(backup),
                    "--target-dsn",
                    str(recovered),
                    "--apply",
                ]
            )
            == 0
        )
        recovered_paths[name] = str(recovered)

    recovered_settings = Settings(
        graph_persistence_mode="native",
        checkpoint_backend="sqlite",
        checkpoint_dsn=recovered_paths["checkpoint"],
        request_ledger_backend="sqlite",
        request_ledger_dsn=recovered_paths["ledger"],
        memory_enabled=True,
        memory_backend="sqlite",
        memory_dsn=recovered_paths["memory"],
        cache_backend="sqlite",
        cache_dsn=recovered_paths["cache"],
        event_store_backend="sqlite",
        event_store_dsn=recovered_paths["events"],
        hitl_enabled=True,
    )
    async with open_agent_runtime(recovered_settings, deps_factory=deps_factory) as facade:
        resumed = await facade.resume(
            request.session_id,
            AgentResume(
                interrupt_id=first.interrupt.interrupt_id,
                value={"action": "approve"},
            ),
            context,
        )
    assert resumed.response is not None
    assert resumed.response.status.value == "success"

    memory = SQLiteMemoryAdapter(recovered_paths["memory"])
    await memory.setup()
    try:
        records = await memory.list_memories("owner-a")
        assert len(records) == 1
        assert records[0].memory_key == "max_price"
    finally:
        await memory.close()

    event_store = SQLiteEventStoreAdapter(recovered_paths["events"])
    await event_store.setup()
    try:
        events = await event_store.list_turn(request.session_id, first.interrupt.turn_id)
        event_types = {event.event_type for event in events}
        assert {"agent_interrupted", "agent_resumed", "agent_completed"} <= event_types
    finally:
        await event_store.close()

    async with open_agent_runtime(recovered_settings, deps_factory=deps_factory) as facade:
        replay = await facade.start(request, context)
    assert replay.response is not None
    assert replay.response.model_dump(mode="json") == resumed.response.model_dump(mode="json")


@pytest.mark.asyncio
async def test_legacy_runtime_sets_up_and_closes_sqlite_checkpoint(
    taxonomy: Any, tmp_path: Any
) -> None:
    checkpoint_path = tmp_path / "legacy-checkpoint.db"
    settings = Settings(
        graph_persistence_mode="legacy",
        checkpoint_backend="sqlite",
        checkpoint_dsn=str(checkpoint_path),
        request_ledger_backend="sqlite",
        request_ledger_dsn=str(tmp_path / "legacy-ledger.db"),
    )

    def deps_factory(_: Settings) -> Any:
        retrieval = FakeRetrieval()
        retrieval.sequence = [two_candidate_result()]
        deps, _ = make_deps(taxonomy, settings, retrieval=retrieval)
        deps.checkpoint = SQLiteCheckpointAdapter(str(checkpoint_path))
        return deps

    request = AgentRequest(session_id="legacy-runtime", request_id="r1", text="索尼耳机")
    async with open_agent_runtime(settings, deps_factory=deps_factory) as facade:
        response = await facade.run(request)

    assert response.session_id == "legacy-runtime"
    assert checkpoint_path.exists()


@pytest.mark.asyncio
async def test_runtime_closes_trace_when_later_resource_setup_fails(
    taxonomy: Any, tmp_path: Any
) -> None:
    events: list[str] = []
    trace = _ClosableTrace(events)
    vision = _ClosableVision(events)
    retrieval = _ClosableRetrieval(events)
    settings = Settings(
        graph_persistence_mode="legacy",
        checkpoint_backend="sqlite",
        checkpoint_dsn=str(tmp_path / "checkpoint.db"),
        request_ledger_backend="disabled",
        memory_backend="sqlite",
        memory_dsn=str(tmp_path / "missing-parent" / "memory.db"),
    )

    def deps_factory(_: Settings) -> Any:
        deps, _ = make_deps(
            taxonomy,
            settings,
            vision=vision,
            retrieval=retrieval,
            trace=trace,  # type: ignore[arg-type]
        )
        return deps

    with pytest.raises(sqlite3.OperationalError, match="unable to open database file"):
        async with open_agent_runtime(settings, deps_factory=deps_factory):
            raise AssertionError("runtime setup should fail before yielding")

    assert trace.close_calls == 1
    assert events == ["retrieval", "vision", "trace"]
    assert vision.close_calls == 1
    assert retrieval.close_calls == 1


@pytest.mark.asyncio
async def test_runtime_closes_model_and_retrieval_before_trace_on_exit(
    taxonomy: Any, tmp_path: Any
) -> None:
    events: list[str] = []
    trace = _ClosableTrace(events)
    vision = _ClosableVision(events)
    retrieval = _ClosableRetrieval(events)
    settings = Settings(
        graph_persistence_mode="legacy",
        checkpoint_backend="sqlite",
        checkpoint_dsn=str(tmp_path / "checkpoint.db"),
        request_ledger_backend="disabled",
    )

    def deps_factory(_: Settings) -> Any:
        deps, _ = make_deps(
            taxonomy,
            settings,
            vision=vision,
            retrieval=retrieval,
            trace=trace,
        )
        return deps

    async with open_agent_runtime(settings, deps_factory=deps_factory):
        pass

    assert events == ["retrieval", "vision", "trace"]
    assert vision.close_calls == 1
    assert retrieval.close_calls == 1
    assert trace.close_calls == 1
