"""二期可靠性组件的离线契约测试。"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from typing import TypedDict

import pytest
from langgraph.graph import END, START, StateGraph

from shijiajing_agent.adapters.ark_models import ModelCallRecord, record_model_call
from shijiajing_agent.adapters.cache import (
    InMemoryVersionedCache,
    canonical_cache_key,
)
from shijiajing_agent.adapters.event_store import (
    InMemoryEventStore,
    SQLiteEventStoreAdapter,
    make_event_store_adapter,
    memory_event_attempt,
    stable_event_id,
)
from shijiajing_agent.adapters.langgraph_persistence import (
    _serializer,
    open_graph_checkpointer,
)
from shijiajing_agent.adapters.memory import SQLiteMemoryAdapter
from shijiajing_agent.adapters.request_ledger import (
    InMemoryRequestLedger,
    SQLiteRequestLedgerAdapter,
)
from shijiajing_agent.config import Settings
from shijiajing_agent.contracts import (
    AgentEventRecord,
    AgentRequest,
    AgentResponse,
    AgentStatus,
    ConversationTurnSummary,
    ImageContentType,
    ImageRef,
    MemoryApplyMode,
    MemoryDirective,
    MemoryMutation,
    MemoryOperation,
    MemoryQuery,
    MemoryStatus,
    RetrievalQuery,
)
from shijiajing_agent.domain.memory_policy import build_memory_mutation
from shijiajing_agent.errors import (
    InvalidRequestError,
    MemoryConflictError,
    RequestLedgerUnavailableError,
)
from shijiajing_agent.nodes.node_support import record_cache_event, timed


def _response(request_id: str = "r1") -> AgentResponse:
    return AgentResponse(
        session_id="s1",
        request_id=request_id,
        turn_id="t1",
        status=AgentStatus.SUCCESS,
        message="ok",
        trace_id="tr1",
    )


def test_memory_event_attempt_is_stable_for_legacy_non_hex_id() -> None:
    legacy_id = "g" * 64
    assert memory_event_attempt(legacy_id) == memory_event_attempt(legacy_id)
    assert memory_event_attempt(legacy_id) >= 0


@pytest.mark.asyncio
async def test_sqlite_request_ledger_is_idempotent(tmp_path: Path) -> None:
    ledger = SQLiteRequestLedgerAdapter(str(tmp_path / "ledger.db"))
    await ledger.setup()
    response = _response()
    await ledger.save_response("s1", "r1", response)
    await ledger.save_response("s1", "r1", response.model_copy(deep=True))
    assert await ledger.get_response("s1", "r1") == response
    await ledger.close()


@pytest.mark.asyncio
async def test_inmemory_request_ledger_uses_defensive_snapshots() -> None:
    ledger = InMemoryRequestLedger()
    response = _response()
    await ledger.save_response("s1", "r1", response)

    response.message = "caller mutation"
    stored = await ledger.get_response("s1", "r1")
    assert stored is not None
    assert stored.message == "ok"

    stored.message = "read mutation"
    reread = await ledger.get_response("s1", "r1")
    assert reread is not None
    assert reread.message == "ok"


@pytest.mark.asyncio
async def test_sqlite_request_ledger_rejects_response_hash_mismatch(tmp_path: Path) -> None:
    path = tmp_path / "ledger-integrity.db"
    ledger = SQLiteRequestLedgerAdapter(str(path))
    await ledger.setup()
    response = _response()
    await ledger.save_response("s1", "r1", response)
    tampered = response.model_dump(mode="json")
    tampered["message"] = "tampered"
    with sqlite3.connect(path) as conn:
        conn.execute(
            "UPDATE agent_request_result SET response_json = ?"
            " WHERE session_id = ? AND request_id = ?",
            (json.dumps(tampered, ensure_ascii=False), "s1", "r1"),
        )
        conn.commit()

    with pytest.raises(RequestLedgerUnavailableError, match="摘要不一致"):
        await ledger.get_response("s1", "r1")
    await ledger.close()


@pytest.mark.asyncio
async def test_cache_adapter_does_not_persist_sensitive_text_key() -> None:
    cache = InMemoryVersionedCache()
    await cache.set(
        "query_rewrite",
        "k",
        {
            "text": "完整用户文本",
            "prompt": "完整 Prompt",
            "explanation_text": "非 explanation namespace 不应保存",
            "retrieval_query": {"query_text": "派生查询", "hard_filters": {}},
        },
        60,
    )
    stored = await cache.get("query_rewrite", "k")
    assert stored == {"retrieval_query": {"query_text": "派生查询", "hard_filters": {}}}
    assert "完整用户文本" not in json.dumps(stored, ensure_ascii=False)
    assert "完整 Prompt" not in json.dumps(stored, ensure_ascii=False)
    assert "非 explanation namespace 不应保存" not in json.dumps(stored, ensure_ascii=False)


def test_persistence_serializer_redacts_request_image_summary_and_query() -> None:
    request = AgentRequest(
        session_id="s-safe",
        request_id="r-safe",
        text="完整用户文本",
        image=ImageRef(
            image_id="img-1",
            uri="data:image/png;base64,AAAA",
            content_type=ImageContentType.PNG,
            sha256="a" * 64,
        ),
    )
    summary = ConversationTurnSummary(
        request_id="r-safe",
        turn_id="t-safe",
        user_text="完整用户文本",
        created_at="2026-08-22T00:00:00+00:00",
    )
    query = RetrievalQuery(query_text="完整用户文本")

    serializer = _serializer()
    kind, encoded = serializer.dumps_typed({"request": request, "summary": summary, "query": query})
    restored = serializer.loads_typed((kind, encoded))

    safe_request = restored["request"]
    assert isinstance(safe_request, AgentRequest)
    assert safe_request.text is None
    assert safe_request.image is not None
    assert safe_request.image.uri.startswith("https://redacted.invalid/image/")
    assert safe_request.metadata["request_text_length"] == 6
    assert "完整用户文本" not in encoded.decode("utf-8", errors="ignore")

    safe_summary = restored["summary"]
    assert isinstance(safe_summary, ConversationTurnSummary)
    assert safe_summary.user_text is None
    assert safe_summary.user_text_sha256 is not None
    assert safe_summary.user_text_length == 6

    safe_query = restored["query"]
    assert isinstance(safe_query, RetrievalQuery)
    assert safe_query.query_text == ""


@pytest.mark.asyncio
async def test_sqlite_memory_is_owner_isolated_and_replay_safe(tmp_path: Path) -> None:
    memory = SQLiteMemoryAdapter(str(tmp_path / "memory.db"))
    await memory.setup()
    directive = MemoryDirective(
        operation=MemoryOperation.UPSERT,
        memory_key="max_price",
        value=1000,
        apply_mode=MemoryApplyMode.CONSTRAINT_DEFAULT,
    )
    mutation = build_memory_mutation("owner-a", "s1", "r1", 0, directive)
    records = await memory.commit("owner-a", [mutation, mutation])
    assert len(records) == 1
    query = MemoryQuery(scope_keys=["global"], limit=20)
    assert len(await memory.recall("owner-a", query)) == 1
    assert await memory.recall("owner-b", query) == []
    await memory.close()


@pytest.mark.asyncio
async def test_sqlite_memory_adapter_rejects_unvalidated_mutation(tmp_path: Path) -> None:
    memory = SQLiteMemoryAdapter(str(tmp_path / "memory-boundary.db"))
    await memory.setup()
    mutation = MemoryMutation(
        mutation_id="a" * 64,
        operation=MemoryOperation.UPSERT,
        memory_key="unknown_key",
        value={"free_form": True},
        apply_mode=MemoryApplyMode.CONSTRAINT_DEFAULT,
        source_session_id="s1",
        source_request_id="r1",
    )

    with pytest.raises(InvalidRequestError, match="不允许的 memory_key"):
        await memory.commit("owner-a", [mutation])

    assert await memory.list_memories("owner-a") == []
    await memory.close()


@pytest.mark.asyncio
async def test_sqlite_memory_rejects_same_mutation_id_with_different_payload(
    tmp_path: Path,
) -> None:
    memory = SQLiteMemoryAdapter(str(tmp_path / "memory-conflict.db"))
    await memory.setup()
    original = build_memory_mutation(
        "owner-a",
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
    conflicting = original.model_copy(update={"value": 900.0})
    await memory.commit("owner-a", [original])

    with pytest.raises(MemoryConflictError, match="mutation_id 内容不一致"):
        await memory.commit("owner-a", [conflicting])

    records = await memory.list_memories("owner-a")
    assert len(records) == 1
    assert records[0].value == 1000.0
    await memory.close()


@pytest.mark.asyncio
async def test_sqlite_memory_overwrite_forget_and_clear_keep_owner_boundary(tmp_path: Path) -> None:
    memory = SQLiteMemoryAdapter(str(tmp_path / "memory-lifecycle.db"))
    await memory.setup()
    query = MemoryQuery(scope_keys=["global"], limit=20)

    first = build_memory_mutation(
        "owner-a",
        "session-a",
        "r1",
        0,
        MemoryDirective(
            operation=MemoryOperation.UPSERT,
            memory_key="max_price",
            value=1000,
            apply_mode=MemoryApplyMode.CONSTRAINT_DEFAULT,
        ),
    )
    second = build_memory_mutation(
        "owner-a",
        "session-a",
        "r2",
        1,
        MemoryDirective(
            operation=MemoryOperation.UPSERT,
            memory_key="max_price",
            value=800,
            apply_mode=MemoryApplyMode.CONSTRAINT_DEFAULT,
        ),
    )
    await memory.commit("owner-a", [first])
    updated = await memory.commit("owner-a", [second])
    assert updated[0].value == 800.0
    assert updated[0].version == 2

    owner_b = build_memory_mutation(
        "owner-b",
        "session-b",
        "r1",
        0,
        MemoryDirective(
            operation=MemoryOperation.UPSERT,
            memory_key="max_price",
            value=1200,
            apply_mode=MemoryApplyMode.CONSTRAINT_DEFAULT,
        ),
    )
    await memory.commit("owner-b", [owner_b])

    forgotten = build_memory_mutation(
        "owner-a",
        "session-a",
        "r3",
        0,
        MemoryDirective(operation=MemoryOperation.FORGET, memory_key="max_price"),
    )
    forgotten_records = await memory.commit("owner-a", [forgotten])
    assert forgotten_records[0].status is MemoryStatus.FORGOTTEN
    assert await memory.recall("owner-a", query) == []
    assert len(await memory.recall("owner-b", query)) == 1

    replacement = build_memory_mutation(
        "owner-a",
        "session-a",
        "r4",
        0,
        MemoryDirective(
            operation=MemoryOperation.UPSERT,
            memory_key="max_price",
            value=900,
            apply_mode=MemoryApplyMode.CONSTRAINT_DEFAULT,
        ),
    )
    await memory.commit("owner-a", [replacement])
    await memory.clear_owner("owner-a", "c" * 64)
    assert await memory.recall("owner-a", query) == []
    assert all(
        item.status is MemoryStatus.FORGOTTEN for item in await memory.list_memories("owner-a")
    )
    assert len(await memory.recall("owner-b", query)) == 1
    await memory.close()


@pytest.mark.asyncio
async def test_cache_key_is_canonical_and_cache_round_trip() -> None:
    assert canonical_cache_key({"a": 1, "b": 2}) == canonical_cache_key({"b": 2, "a": 1})
    cache = InMemoryVersionedCache()
    await cache.set("intent", "k", {"answer": "ok"}, 60)
    assert await cache.get("intent", "k") == {"answer": "ok"}


@pytest.mark.asyncio
async def test_inmemory_cache_returns_defensive_nested_copy() -> None:
    cache = InMemoryVersionedCache()
    await cache.set("intent", "nested", {"safe": {"value": 1}}, 60)
    value = await cache.get("intent", "nested")
    assert value is not None
    value["safe"]["value"] = 2
    reread = await cache.get("intent", "nested")
    assert reread == {"safe": {"value": 1}}


@pytest.mark.asyncio
async def test_event_store_replay_is_idempotent() -> None:
    event_id = stable_event_id("s1", "r1", "t1", "supervisor", None, "agent_started", 0)
    event = AgentEventRecord(
        event_id=event_id,
        session_id="s1",
        request_id="r1",
        turn_id="t1",
        trace_id="tr1",
        agent_name="supervisor",
        node_name=None,
        event_type="agent_started",
        occurred_at="2026-08-22T00:00:00+00:00",
    )
    store = InMemoryEventStore()
    await store.append(event)
    await store.append(event.model_copy(deep=True))
    assert len(await store.list_turn("s1", "t1")) == 1


@pytest.mark.asyncio
async def test_inmemory_event_store_orders_and_copies_events() -> None:
    events = [
        AgentEventRecord(
            event_id=stable_event_id("s-order", "r1", "t1", "supervisor", None, kind, 0),
            session_id="s-order",
            request_id="r1",
            turn_id="t1",
            trace_id="tr1",
            agent_name="supervisor",
            node_name=None,
            event_type=kind,
            payload={"safe": {"value": index}},
            occurred_at="2026-08-22T00:00:00+00:00",
        )
        for index, kind in enumerate(("event_a", "event_b"))
    ]
    store = InMemoryEventStore()
    await store.append(events[1])
    await store.append(events[0])

    listed = await store.list_turn("s-order", "t1")
    assert [event.event_id for event in listed] == sorted(event.event_id for event in events)
    listed[0].payload["safe"]["value"] = 999
    reread = await store.list_turn("s-order", "t1")
    assert reread[0].payload["safe"]["value"] != 999


@pytest.mark.asyncio
async def test_event_store_same_timestamp_keeps_hitl_lifecycle_order() -> None:
    events = [
        AgentEventRecord(
            event_id=stable_event_id("s-hitl-order", "r1", "t1", "supervisor", None, kind, 0),
            session_id="s-hitl-order",
            request_id="r1",
            turn_id="t1",
            trace_id="tr1",
            agent_name="supervisor",
            node_name=None,
            event_type=kind,
            occurred_at="2026-08-22T00:00:00+00:00",
        )
        for kind in ("agent_started", "agent_interrupted", "agent_resumed", "agent_completed")
    ]
    store = InMemoryEventStore()
    for event in reversed(events):
        await store.append(event)

    assert [event.event_type for event in await store.list_turn("s-hitl-order", "t1")] == [
        "agent_started",
        "agent_interrupted",
        "agent_resumed",
        "agent_completed",
    ]


@pytest.mark.asyncio
async def test_sqlite_event_store_concurrent_replay_is_idempotent(tmp_path: Path) -> None:
    event_id = stable_event_id("s-concurrent", "r1", "t1", "supervisor", None, "agent_started", 0)
    event = AgentEventRecord(
        event_id=event_id,
        session_id="s-concurrent",
        request_id="r1",
        turn_id="t1",
        trace_id="tr1",
        agent_name="supervisor",
        node_name=None,
        event_type="agent_started",
        occurred_at="2026-08-22T00:00:00+00:00",
    )
    store_a = SQLiteEventStoreAdapter(str(tmp_path / "events.db"))
    store_b = SQLiteEventStoreAdapter(str(tmp_path / "events.db"))
    await store_a.setup()
    await store_b.setup()
    try:
        await asyncio.gather(
            *(store.append(event.model_copy(deep=True)) for store in [store_a, store_b] * 8)
        )
        assert len(await store_a.list_turn("s-concurrent", "t1")) == 1
    finally:
        await store_a.close()
        await store_b.close()


def test_disabled_event_store_is_not_attached() -> None:
    assert make_event_store_adapter("disabled", None) is None


@pytest.mark.asyncio
async def test_cache_audit_events_keep_only_namespace_and_hash() -> None:
    store = InMemoryEventStore()
    deps = SimpleNamespace(
        event_store=store,
        metrics=SimpleNamespace(inc=lambda *args, **kwargs: None),
    )
    state = {
        "current_request": AgentRequest(session_id="s-cache", request_id="r1", text="用户文本"),
        "turn_id": "t1",
        "trace_id": "tr1",
        "node_events": [],
    }
    cache_key = "a" * 64
    await record_cache_event(
        deps,
        state,
        node_name="parse_intent",
        namespace="intent",
        cache_key=cache_key,
        hit=False,
    )
    await record_cache_event(
        deps,
        state,
        node_name="parse_intent",
        namespace="intent",
        cache_key=cache_key,
        hit=True,
    )
    events = await store.list_turn("s-cache", "t1")
    assert [event.event_type for event in events] == ["cache_miss", "cache_hit"]
    assert events[0].payload == {"namespace": "intent", "cache_key": cache_key}
    assert "用户文本" not in str(events[0].model_dump(mode="json"))

    class Trace:
        def __init__(self) -> None:
            self.events = []

        async def emit(self, event: object) -> None:
            self.events.append(event)

    trace = Trace()
    no_store_deps = SimpleNamespace(event_store=None, trace=trace, metrics=deps.metrics)
    await record_cache_event(
        no_store_deps,
        state,
        node_name="parse_intent",
        namespace="intent",
        cache_key=cache_key,
        hit=True,
    )
    assert len(trace.events) == 1
    assert trace.events[0].cache_hit is True


@pytest.mark.asyncio
async def test_native_sqlite_checkpointer_setup(tmp_path: Path) -> None:
    settings = Settings(
        checkpoint_backend="sqlite",
        checkpoint_dsn=str(tmp_path / "native.db"),
    )
    async with open_graph_checkpointer(settings) as saver:
        assert saver is not None


@pytest.mark.asyncio
async def test_native_sqlite_checkpointer_redacts_persisted_request(tmp_path: Path) -> None:
    settings = Settings(
        checkpoint_backend="sqlite",
        checkpoint_dsn=str(tmp_path / "native-redaction.db"),
    )

    class NativeState(TypedDict):
        request: AgentRequest

    graph = StateGraph(NativeState)
    graph.add_node("finish", lambda state: {})
    graph.add_edge(START, "finish")
    graph.add_edge("finish", END)
    request = AgentRequest(
        session_id="s-native-safe",
        request_id="r-native-safe",
        text="完整用户文本",
        image=ImageRef(
            image_id="img-native",
            uri="data:image/png;base64,BBBB",
            content_type=ImageContentType.PNG,
            sha256="c" * 64,
        ),
    )
    config = {"configurable": {"thread_id": "s-native-safe"}}

    async with open_graph_checkpointer(settings) as saver:
        compiled = graph.compile(checkpointer=saver)
        await compiled.ainvoke({"request": request}, config)
        snapshot = await compiled.aget_state(config)

    stored_request = snapshot.values["request"]
    assert isinstance(stored_request, AgentRequest)
    assert stored_request.text is None
    assert stored_request.image is not None
    assert stored_request.image.uri.startswith("https://redacted.invalid/image/")


@pytest.mark.asyncio
async def test_timed_node_projects_model_call_metadata() -> None:
    @timed("parse_intent")
    async def node(state: dict[str, object]) -> dict[str, object]:
        record_model_call(
            ModelCallRecord(
                node="parse_intent",
                prompt_version="v1",
                model="text-model",
                duration_ms=4.0,
                input_hash="i" * 64,
                output_hash="o" * 64,
                success=True,
                token_usage={"total_tokens": 8},
            )
        )
        return {}

    events = (
        await node(
            {
                "session_id": "s1",
                "request_id": "r1",
                "turn_id": "t1",
                "trace_id": "tr1",
                "node_events": [],
            }
        )
    )["node_events"]
    assert events[0]["model"] == "text-model"
    assert events[0]["prompt_version"] == "v1"
    assert events[0]["token_usage"] == {"total_tokens": 8}
