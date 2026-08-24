"""native thread 的暂停/恢复最小回归。"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from langgraph.checkpoint.memory import MemorySaver

from shijiajing_agent.adapters.event_store import InMemoryEventStore
from shijiajing_agent.adapters.memory import SQLiteMemoryAdapter
from shijiajing_agent.adapters.request_ledger import InMemoryRequestLedger
from shijiajing_agent.contracts import (
    AgentExecutionContext,
    AgentRequest,
    AgentResume,
    AgentStatus,
    IntentPatch,
    MemoryApplyMode,
    MemoryDirective,
    MemoryOperation,
    RecognitionResult,
)
from shijiajing_agent.errors import RequestLedgerUnavailableError
from shijiajing_agent.facade import AgentFacade
from shijiajing_agent.nodes.input_nodes import make_initial_state
from shijiajing_agent.ports.retrieval import RetrievalResult

from .conftest import (
    FakeRetrieval,
    candidate,
    make_deps,
    make_image,
    two_candidate_result,
)
from .conftest import WorkflowSettings as Settings


def _without_runtime_ids(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _without_runtime_ids(item)
            for key, item in value.items()
            if key not in {"turn_id", "trace_id", "updated_turn_id"}
        }
    if isinstance(value, list):
        return [_without_runtime_ids(item) for item in value]
    return value


@pytest.mark.asyncio
async def test_legacy_start_rejects_memory_context_without_native(taxonomy: Any) -> None:
    deps, _ = make_deps(taxonomy, Settings())
    facade = AgentFacade(deps)

    result = await facade.start(
        AgentRequest(session_id="legacy-memory", request_id="r1", text="索尼耳机"),
        AgentExecutionContext(memory_owner_id="owner-a", memory_enabled=True),
    )

    assert result.response is not None
    assert result.response.status is AgentStatus.FAILED
    assert result.response.message == "启用记忆需要 native persistence，请使用 native runtime。"


@pytest.mark.asyncio
async def test_native_turn_emits_trace_and_event_store_node_events(taxonomy: Any) -> None:
    deps, fakes = make_deps(taxonomy, Settings())
    deps.graph_checkpointer = MemorySaver()
    deps.event_store = InMemoryEventStore()
    facade = AgentFacade(deps)

    result = await facade.start(
        AgentRequest(session_id="native-events", request_id="r1", text="帮我比个价"),
        AgentExecutionContext(),
    )

    assert result.response is not None
    event_types = [event.event_type.value for event in fakes["trace"].events]
    assert event_types[0] == "turn_started"
    assert "node_completed" in event_types
    assert event_types[-1] in {"results_ready", "turn_failed"}
    records = await deps.event_store.list_turn("native-events", result.response.turn_id)
    assert any(record.node_name == "parse_intent" for record in records)


@pytest.mark.asyncio
async def test_subgraph_boundary_failure_emits_child_agent_failure(taxonomy: Any) -> None:
    deps, _ = make_deps(taxonomy, Settings())
    deps.event_store = InMemoryEventStore()
    facade = AgentFacade(deps)
    request = AgentRequest(session_id="subgraph-failure", request_id="r1", text="找耳机")
    state = make_initial_state(request, None)
    failure = RuntimeError("invalid subgraph output")
    attribute_name = "node_name"
    setattr(failure, attribute_name, "intent_subgraph")

    await facade._emit_agent_failure_from_exception(state, failure)

    records = await deps.event_store.list_turn("subgraph-failure", state["turn_id"])
    intent_events = [record for record in records if record.agent_name == "intent"]
    assert [record.event_type for record in intent_events] == [
        "agent_started",
        "agent_failed",
    ]


@pytest.mark.asyncio
async def test_native_new_turn_resets_previous_working_results(taxonomy: Any) -> None:
    """同一 native thread 的新请求不能复用上一轮的查询、候选或响应。"""
    retrieval = FakeRetrieval()
    retrieval.sequence = [two_candidate_result()]
    deps, _ = make_deps(taxonomy, Settings(), retrieval=retrieval)
    deps.graph_checkpointer = MemorySaver()
    deps.event_store = InMemoryEventStore()
    facade = AgentFacade(deps)

    first = await facade.start(
        AgentRequest(session_id="native-new-turn", request_id="r1", text="索尼耳机"),
        AgentExecutionContext(),
    )
    assert first.response is not None
    assert first.response.status == AgentStatus.SUCCESS
    assert first.response.groups

    second = await facade.start(
        AgentRequest(session_id="native-new-turn", request_id="r2", text="帮我找手机"),
        AgentExecutionContext(),
    )

    assert second.response is not None
    assert second.response.request_id == "r2"
    assert second.response.status == AgentStatus.NO_RESULTS
    assert second.response.groups == []
    assert retrieval.calls == 2
    assert retrieval.last_query is not None
    assert retrieval.last_query.query_text == "帮我找手机"

    records = await deps.event_store.list_turn("native-new-turn", second.response.turn_id)
    parse_events = [
        record
        for record in records
        if record.node_name == "parse_intent" and record.event_type == "node_completed"
    ]
    assert parse_events
    assert [record.payload["retry_count"] for record in parse_events] == [0]


@pytest.mark.asyncio
async def test_native_recent_turns_are_independent_of_long_term_memory(taxonomy: Any) -> None:
    """bounded conversation memory 必须在长期 Memory 关闭时仍跨 turn 保留。"""
    retrieval = FakeRetrieval()
    retrieval.sequence = [two_candidate_result(), two_candidate_result()]
    deps, _ = make_deps(taxonomy, Settings(), retrieval=retrieval)
    deps.graph_checkpointer = MemorySaver()
    facade = AgentFacade(deps)

    first = await facade.start(
        AgentRequest(session_id="native-recent-turns", request_id="r1", text="索尼耳机"),
        AgentExecutionContext(),
    )
    second = await facade.start(
        AgentRequest(session_id="native-recent-turns", request_id="r2", text="索尼耳机"),
        AgentExecutionContext(),
    )

    assert first.response is not None
    assert second.response is not None
    snapshot = await facade._graph.aget_state(
        {"configurable": {"thread_id": "native-recent-turns"}}
    )
    assert [summary.request_id for summary in snapshot.values["recent_turns"]] == ["r1", "r2"]


@pytest.mark.asyncio
async def test_native_replay_start_returns_existing_interrupt(taxonomy: Any) -> None:
    """active interrupt 未恢复前，重放原 request 不得覆盖 checkpoint。"""
    deps, _ = make_deps(taxonomy, Settings(hitl_enabled=True))
    deps.graph_checkpointer = MemorySaver()
    deps.event_store = InMemoryEventStore()
    facade = AgentFacade(deps)
    request = AgentRequest(
        session_id="native-replay-interrupt",
        request_id="r1",
        text="帮我比个价",
    )
    context = AgentExecutionContext()

    first = await facade.start(request, context)
    assert first.interrupt is not None

    replay = await facade.start(request, context)
    assert replay.interrupt is not None
    assert replay.interrupt.model_dump(mode="json") == first.interrupt.model_dump(mode="json")

    rejected = await facade.start(
        AgentRequest(session_id="native-replay-interrupt", request_id="r2", text="索尼耳机"),
        context,
    )
    assert rejected.response is not None
    assert rejected.response.status == AgentStatus.FAILED

    resumed = await facade.resume(
        request.session_id,
        AgentResume(
            interrupt_id=first.interrupt.interrupt_id,
            value={"action": "answer", "text": "索尼耳机"},
        ),
        context,
    )
    assert resumed.response is not None

    records = await deps.event_store.list_turn(request.session_id, first.interrupt.turn_id)
    interrupted_events = [
        record.event_type for record in records if record.event_type == "agent_interrupted"
    ]
    assert interrupted_events == ["agent_interrupted"]


@pytest.mark.asyncio
async def test_native_start_maps_locked_ledger_read_failure(taxonomy: Any) -> None:
    deps, _ = make_deps(taxonomy, Settings())
    deps.graph_checkpointer = MemorySaver()
    ledger = InMemoryRequestLedger()
    calls = 0

    async def get_response(session_id: str, request_id: str) -> Any:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RequestLedgerUnavailableError("injected ledger read outage")
        return None

    ledger.get_response = get_response
    deps.request_ledger = ledger
    facade = AgentFacade(deps)

    result = await facade.start(
        AgentRequest(session_id="native-ledger-read", request_id="r1", text="索尼耳机"),
        AgentExecutionContext(),
    )

    assert result.response is not None
    assert result.response.status == AgentStatus.FAILED
    assert result.response.message == "请求结果账本不可用，请稍后重试。"
    assert calls == 2


@pytest.mark.asyncio
async def test_native_resume_maps_checkpoint_read_failure(taxonomy: Any) -> None:
    deps, _ = make_deps(taxonomy, Settings(hitl_enabled=True))
    deps.graph_checkpointer = MemorySaver()
    facade = AgentFacade(deps)

    async def fail_get_state(config: Any) -> Any:
        del config
        raise RuntimeError("injected checkpoint read outage")

    facade._graph.aget_state = fail_get_state
    result = await facade.resume(
        "native-checkpoint-read",
        AgentResume(interrupt_id="0" * 64, value={}),
        AgentExecutionContext(),
    )

    assert result.response is not None
    assert result.response.status == AgentStatus.FAILED
    assert result.response.message == "状态存储不可用，请稍后重试。"


@pytest.mark.asyncio
async def test_native_resume_maps_ledger_save_failure(taxonomy: Any) -> None:
    deps, _ = make_deps(taxonomy, Settings(hitl_enabled=True))
    deps.graph_checkpointer = MemorySaver()
    ledger = InMemoryRequestLedger()
    deps.request_ledger = ledger
    facade = AgentFacade(deps)
    started = await facade.start(
        AgentRequest(session_id="native-ledger-save", request_id="r1", text="帮我比个价"),
        AgentExecutionContext(),
    )
    assert started.interrupt is not None

    async def fail_save(*args: Any, **kwargs: Any) -> None:
        del args, kwargs
        raise RequestLedgerUnavailableError("injected ledger write outage")

    ledger.save_response = fail_save
    result = await facade.resume(
        "native-ledger-save",
        AgentResume(
            interrupt_id=started.interrupt.interrupt_id,
            value={"action": "answer", "text": "索尼耳机"},
        ),
        AgentExecutionContext(),
    )

    assert result.response is not None
    assert result.response.status == AgentStatus.FAILED
    assert result.response.message == "请求结果账本不可用，请稍后重试。"


@pytest.mark.asyncio
async def test_native_resume_maps_timeout_and_releases_fence(taxonomy: Any) -> None:
    deps, _ = make_deps(taxonomy, Settings(hitl_enabled=True))
    deps.graph_checkpointer = MemorySaver()
    facade = AgentFacade(deps)
    started = await facade.start(
        AgentRequest(session_id="native-resume-timeout", request_id="r1", text="帮我比个价"),
        AgentExecutionContext(),
    )
    assert started.interrupt is not None
    deps.settings = Settings(hitl_enabled=True, turn_timeout_seconds=0.001)

    async def slow_astream(*args: Any, **kwargs: Any):
        del args, kwargs
        await asyncio.sleep(0.02)
        if False:
            yield {}

    facade._graph.astream = slow_astream
    result = await facade.resume(
        "native-resume-timeout",
        AgentResume(
            interrupt_id=started.interrupt.interrupt_id,
            value={"action": "answer", "text": "索尼耳机"},
        ),
        AgentExecutionContext(),
    )

    assert result.response is not None
    assert result.response.status == AgentStatus.FAILED
    assert result.response.message == "处理超时，请稍后重试。"
    assert (
        "native-resume-timeout",
        started.interrupt.interrupt_id,
    ) not in deps.checkpoint.resume_claims


@pytest.mark.asyncio
async def test_native_completed_request_replays_from_checkpoint_without_ledger(
    taxonomy: Any,
) -> None:
    """没有 Request Ledger 时，native checkpoint 仍提供同 request_id 幂等兜底。"""
    retrieval = FakeRetrieval()
    retrieval.sequence = [two_candidate_result()]
    deps, _ = make_deps(taxonomy, Settings(), retrieval=retrieval)
    deps.graph_checkpointer = MemorySaver()
    facade = AgentFacade(deps)
    request = AgentRequest(session_id="native-completed-replay", request_id="r1", text="索尼耳机")

    first = await facade.start(request, AgentExecutionContext())
    replay = await facade.start(request, AgentExecutionContext())

    assert first.response is not None
    assert replay.response is not None
    assert replay.response.model_dump(mode="json") == first.response.model_dump(mode="json")
    assert retrieval.calls == 1


@pytest.mark.asyncio
async def test_native_checkpoint_replay_repairs_missing_ledger_record(taxonomy: Any) -> None:
    """Ledger 短暂写失败后，checkpoint replay 必须在恢复时补写 Ledger。"""
    retrieval = FakeRetrieval()
    retrieval.sequence = [two_candidate_result()]
    deps, fakes = make_deps(taxonomy, Settings(), retrieval=retrieval)
    deps.graph_checkpointer = MemorySaver()
    deps.event_store = InMemoryEventStore()
    ledger = InMemoryRequestLedger()
    original_save = ledger.save_response
    failures = 1

    async def fail_first_save(
        session_id: str, request_id: str, response: Any, expected_absent: bool = True
    ) -> None:
        nonlocal failures
        if failures:
            failures -= 1
            raise RequestLedgerUnavailableError("injected ledger outage")
        await original_save(session_id, request_id, response, expected_absent)

    ledger.save_response = fail_first_save
    deps.request_ledger = ledger
    facade = AgentFacade(deps)
    request = AgentRequest(session_id="native-ledger-repair", request_id="r1", text="索尼耳机")

    first = await facade.start(request, AgentExecutionContext())
    assert first.response is not None
    assert first.response.status == AgentStatus.FAILED
    assert await ledger.get_response(request.session_id, request.request_id) is None

    repaired = await facade.start(request, AgentExecutionContext())
    assert repaired.response is not None
    assert repaired.response.status == AgentStatus.SUCCESS
    assert await ledger.get_response(request.session_id, request.request_id) == repaired.response
    assert retrieval.calls == 1
    assert fakes["metrics"].counts["request_ledger_repair_total"] == 1
    repair_events = await deps.event_store.list_turn(request.session_id, repaired.response.turn_id)
    assert [event.event_type for event in repair_events].count("request_ledger_repaired") == 1


@pytest.mark.asyncio
async def test_native_graph_failure_persists_failed_turn(taxonomy: Any) -> None:
    """native 图异常必须保存 FAILED checkpoint、摘要和幂等结果。"""
    deps, _ = make_deps(taxonomy, Settings())
    deps.graph_checkpointer = MemorySaver()
    deps.event_store = InMemoryEventStore()
    deps.request_ledger = InMemoryRequestLedger()
    facade = AgentFacade(deps)
    original_astream = facade._graph.astream
    calls = 0

    async def fail_once(*args: Any, **kwargs: Any):
        nonlocal calls
        del args, kwargs
        calls += 1
        failure = RuntimeError("injected native graph failure")
        attribute_name = "node_name"
        setattr(failure, attribute_name, "parse_intent")
        raise failure
        yield  # pragma: no cover

    facade._graph.astream = fail_once
    request = AgentRequest(session_id="native-failure", request_id="r1", text="索尼耳机")
    first = await facade.start(request, AgentExecutionContext())
    facade._graph.astream = original_astream

    assert first.response is not None
    assert first.response.status == AgentStatus.FAILED
    snapshot = await facade._graph.aget_state({"configurable": {"thread_id": "native-failure"}})
    assert snapshot.values["response"].status == AgentStatus.FAILED
    assert [summary.request_id for summary in snapshot.values["recent_turns"]] == ["r1"]
    records = await deps.event_store.list_turn("native-failure", first.response.turn_id)
    assert [record.event_type for record in records if record.agent_name == "intent"] == [
        "agent_started",
        "agent_failed",
    ]

    replay = await facade.start(request, AgentExecutionContext())
    assert replay.response is not None
    assert replay.response.model_dump(mode="json") == first.response.model_dump(mode="json")
    assert calls == 1


@pytest.mark.asyncio
async def test_native_clarification_interrupt_can_resume(taxonomy: Any) -> None:
    deps, _ = make_deps(taxonomy, Settings(hitl_enabled=True))
    deps.graph_checkpointer = MemorySaver()
    deps.event_store = InMemoryEventStore()
    facade = AgentFacade(deps)
    first = await facade.start(
        AgentRequest(session_id="native-hitl", request_id="r1", text="帮我比个价"),
        AgentExecutionContext(),
    )
    assert first.interrupt is not None
    assert first.interrupt.kind.value == "clarification"
    second = await facade.resume(
        "native-hitl",
        AgentResume(
            interrupt_id=first.interrupt.interrupt_id,
            value={"action": "answer", "text": "索尼耳机"},
        ),
        AgentExecutionContext(),
    )
    assert second.response is not None
    assert second.response.status == AgentStatus.NO_RESULTS
    records = await deps.event_store.list_turn("native-hitl", first.interrupt.turn_id)
    assert [
        record.event_type
        for record in records
        if record.event_type.startswith("agent_") and record.agent_name == "supervisor"
    ] == [
        "agent_started",
        "agent_interrupted",
        "agent_resumed",
        "agent_completed",
    ]
    child_lifecycle: dict[str, set[str]] = {}
    for record in records:
        if record.agent_name != "supervisor" and record.event_type in {
            "agent_started",
            "agent_completed",
            "agent_failed",
        }:
            child_lifecycle.setdefault(record.agent_name, set()).add(record.event_type)
    assert child_lifecycle
    assert all(
        lifecycle & {"agent_completed", "agent_failed"} for lifecycle in child_lifecycle.values()
    )
    interrupted = next(record for record in records if record.event_type == "agent_interrupted")
    resumed = next(record for record in records if record.event_type == "agent_resumed")
    assert interrupted.payload == {
        "interrupt_id": first.interrupt.interrupt_id,
        "interrupt_kind": "clarification",
    }
    assert resumed.payload == interrupted.payload


@pytest.mark.asyncio
async def test_native_repeated_clarification_uses_new_interrupt_id(taxonomy: Any) -> None:
    deps, _ = make_deps(taxonomy, Settings(hitl_enabled=True))
    deps.graph_checkpointer = MemorySaver()
    facade = AgentFacade(deps)

    first = await facade.start(
        AgentRequest(
            session_id="native-repeated-clarification",
            request_id="r1",
            text="帮我比个价",
        ),
        AgentExecutionContext(),
    )
    assert first.interrupt is not None

    second = await facade.resume(
        "native-repeated-clarification",
        AgentResume(
            interrupt_id=first.interrupt.interrupt_id,
            value={"action": "answer", "text": "仍然不知道"},
        ),
        AgentExecutionContext(),
    )
    assert second.interrupt is not None
    assert second.interrupt.kind.value == "clarification"
    assert second.interrupt.interrupt_id != first.interrupt.interrupt_id

    third = await facade.resume(
        "native-repeated-clarification",
        AgentResume(
            interrupt_id=second.interrupt.interrupt_id,
            value={"action": "answer", "text": "索尼耳机"},
        ),
        AgentExecutionContext(),
    )
    assert third.response is not None
    assert third.response.status == AgentStatus.NO_RESULTS


@pytest.mark.asyncio
async def test_native_resume_failure_releases_fence_for_retry(taxonomy: Any) -> None:
    deps, _ = make_deps(taxonomy, Settings(hitl_enabled=True))
    deps.graph_checkpointer = MemorySaver()
    facade = AgentFacade(deps)
    first = await facade.start(
        AgentRequest(session_id="native-retry", request_id="r1", text="帮我比个价"),
        AgentExecutionContext(),
    )
    assert first.interrupt is not None
    resume = AgentResume(
        interrupt_id=first.interrupt.interrupt_id,
        value={"action": "answer", "text": "索尼耳机"},
    )
    original_astream = facade._graph.astream

    async def fail_once(*args: Any, **kwargs: Any):
        del args, kwargs
        raise RuntimeError("injected resume failure")
        yield  # pragma: no cover

    facade._graph.astream = fail_once
    failed = await facade.resume("native-retry", resume, AgentExecutionContext())
    assert failed.response is not None
    assert failed.response.status == AgentStatus.FAILED
    facade._graph.astream = original_astream

    retried = await facade.resume("native-retry", resume, AgentExecutionContext())
    assert retried.response is not None
    assert retried.response.status == AgentStatus.NO_RESULTS


@pytest.mark.asyncio
async def test_native_resume_cancellation_releases_fence_for_retry(taxonomy: Any) -> None:
    deps, _ = make_deps(taxonomy, Settings(hitl_enabled=True))
    deps.graph_checkpointer = MemorySaver()
    facade = AgentFacade(deps)
    first = await facade.start(
        AgentRequest(session_id="native-cancel", request_id="r1", text="帮我比个价"),
        AgentExecutionContext(),
    )
    assert first.interrupt is not None
    resume = AgentResume(
        interrupt_id=first.interrupt.interrupt_id,
        value={"action": "answer", "text": "索尼耳机"},
    )
    original_astream = facade._graph.astream

    async def cancel_once(*args: Any, **kwargs: Any):
        del args, kwargs
        raise asyncio.CancelledError()
        yield  # pragma: no cover

    facade._graph.astream = cancel_once
    with pytest.raises(asyncio.CancelledError):
        await facade.resume("native-cancel", resume, AgentExecutionContext())
    facade._graph.astream = original_astream

    retried = await facade.resume("native-cancel", resume, AgentExecutionContext())
    assert retried.response is not None
    assert retried.response.status == AgentStatus.NO_RESULTS


@pytest.mark.asyncio
async def test_native_recognition_review_can_resume(taxonomy: Any) -> None:
    settings = Settings(hitl_enabled=True)
    deps, fakes = make_deps(taxonomy, settings)
    fakes["vision"].results = [
        RecognitionResult(
            recognition_id="low-confidence",
            category_id="headphone",
            category_name="耳机",
            brand="Sony",
            model="WH-1000XM5",
            field_confidences={"category_id": 0.5, "brand": 0.5, "model": 0.5},
            overall_confidence=0.5,
            unresolved_fields=["color"],
        )
    ]
    deps.graph_checkpointer = MemorySaver()
    deps.event_store = InMemoryEventStore()
    facade = AgentFacade(deps)

    first = await facade.start(
        AgentRequest(
            session_id="native-recognition-review",
            request_id="r1",
            text="找耳机",
            image=make_image(),
        ),
        AgentExecutionContext(),
    )

    assert first.interrupt is not None
    assert first.interrupt.kind.value == "recognition_review"
    second = await facade.resume(
        "native-recognition-review",
        AgentResume(interrupt_id=first.interrupt.interrupt_id, value={"action": "approve"}),
        AgentExecutionContext(),
    )

    assert second.response is not None
    assert second.interrupt is None


@pytest.mark.asyncio
async def test_native_same_item_review_split_can_resume(taxonomy: Any) -> None:
    settings = Settings(hitl_enabled=True, same_item_accept_threshold=0.99)
    retrieval = FakeRetrieval()
    first = candidate("review-a", price=1899.0)
    first = first.model_copy(
        update={"offer": first.offer.model_copy(update={"same_item_key": None})}
    )
    second = candidate("review-b", price=1999.0)
    second = second.model_copy(
        update={"offer": second.offer.model_copy(update={"same_item_key": None})}
    )
    second = second.model_copy(
        update={
            "offer": second.offer.model_copy(
                update={"title": "Sony WH-1000XM5 头戴式降噪耳机 官方"}
            )
        }
    )
    retrieval.sequence = [RetrievalResult(candidates=[first, second], total_found=2)]
    deps, _ = make_deps(taxonomy, settings, retrieval=retrieval)
    deps.graph_checkpointer = MemorySaver()
    deps.event_store = InMemoryEventStore()
    facade = AgentFacade(deps)

    started = await facade.start(
        AgentRequest(session_id="native-same-item-review", request_id="r1", text="索尼耳机"),
        AgentExecutionContext(),
    )

    assert started.interrupt is not None
    assert started.interrupt.kind.value == "same_item_review"
    resumed = await facade.resume(
        "native-same-item-review",
        AgentResume(interrupt_id=started.interrupt.interrupt_id, value={"action": "split"}),
        AgentExecutionContext(),
    )

    assert resumed.response is not None
    assert len(resumed.response.groups) == 2


@pytest.mark.asyncio
async def test_native_resume_rejects_context_mismatch(taxonomy: Any) -> None:
    deps, _ = make_deps(taxonomy, Settings(hitl_enabled=True))
    deps.graph_checkpointer = MemorySaver()
    facade = AgentFacade(deps)

    first = await facade.start(
        AgentRequest(session_id="native-context", request_id="r1", text="帮我比个价"),
        AgentExecutionContext(),
    )
    assert first.interrupt is not None

    rejected = await facade.resume(
        "native-context",
        AgentResume(
            interrupt_id=first.interrupt.interrupt_id, value={"action": "answer", "text": "耳机"}
        ),
        AgentExecutionContext(memory_owner_id="owner-a", memory_enabled=True),
    )

    assert rejected.response is not None
    assert rejected.response.status == AgentStatus.FAILED


@pytest.mark.asyncio
async def test_native_resume_persists_distinct_node_attempts(taxonomy: Any) -> None:
    deps, _ = make_deps(taxonomy, Settings(hitl_enabled=True))
    deps.graph_checkpointer = MemorySaver()
    deps.event_store = InMemoryEventStore()
    facade = AgentFacade(deps)

    first = await facade.start(
        AgentRequest(session_id="native-attempts", request_id="r1", text="帮我比个价"),
        AgentExecutionContext(),
    )
    assert first.interrupt is not None
    second = await facade.resume(
        "native-attempts",
        AgentResume(
            interrupt_id=first.interrupt.interrupt_id,
            value={"action": "answer", "text": "索尼耳机"},
        ),
        AgentExecutionContext(),
    )
    assert second.response is not None
    records = await deps.event_store.list_turn("native-attempts", second.response.turn_id)
    parse_events = [
        record
        for record in records
        if record.node_name == "parse_intent" and record.event_type == "node_completed"
    ]
    assert len(parse_events) == 2
    assert [record.payload["retry_count"] for record in parse_events] == [0, 1]
    assert len({record.event_id for record in parse_events}) == 2


@pytest.mark.asyncio
async def test_native_memory_confirmation_rejects_commit(taxonomy: Any, tmp_path: Any) -> None:
    settings = Settings(hitl_enabled=True, memory_enabled=True)
    deps, fakes = make_deps(taxonomy, settings)
    memory = SQLiteMemoryAdapter(str(tmp_path / "memory.db"))
    await memory.setup()
    deps.memory = memory
    deps.graph_checkpointer = MemorySaver()
    deps.event_store = InMemoryEventStore()
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
    facade = AgentFacade(deps)
    first = await facade.start(
        AgentRequest(session_id="native-memory", request_id="r1", text="找耳机"),
        AgentExecutionContext(memory_owner_id="owner-a", memory_enabled=True),
    )
    assert first.interrupt is not None
    assert first.interrupt.kind.value == "memory_confirmation"
    second = await facade.resume(
        "native-memory",
        AgentResume(
            interrupt_id=first.interrupt.interrupt_id,
            value={"action": "reject"},
        ),
        AgentExecutionContext(memory_owner_id="owner-a", memory_enabled=True),
    )
    assert second.response is not None
    assert await memory.list_memories("owner-a") == []
    records = await deps.event_store.list_turn("native-memory", first.interrupt.turn_id)
    recalled = [record for record in records if record.event_type == "memory_recalled"]
    assert len(recalled) == 1
    assert recalled[0].status == "success"
    assert recalled[0].payload == {"count": 0}
    await memory.close()


@pytest.mark.asyncio
async def test_memory_commit_rollout_flag_skips_confirmation_and_write(
    taxonomy: Any, tmp_path: Any
) -> None:
    settings = Settings(hitl_enabled=True, memory_enabled=True, memory_commit_enabled=False)
    deps, fakes = make_deps(taxonomy, settings)
    memory = SQLiteMemoryAdapter(str(tmp_path / "memory-rollout.db"))
    await memory.setup()
    deps.memory = memory
    deps.graph_checkpointer = MemorySaver()
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

    result = await AgentFacade(deps).start(
        AgentRequest(session_id="native-memory-rollout", request_id="r1", text="找耳机"),
        AgentExecutionContext(memory_owner_id="owner-a", memory_enabled=True),
    )

    assert result.interrupt is None
    assert result.response is not None
    assert await memory.list_memories("owner-a") == []
    await memory.close()


@pytest.mark.asyncio
async def test_legacy_and_native_business_outputs_match(taxonomy: Any) -> None:
    """同一 workflow fixture 下 legacy/native 只允许在运行标识上不同。"""
    request = AgentRequest(session_id="mode-parity", request_id="r1", text="索尼耳机")

    legacy_retrieval = FakeRetrieval()
    legacy_retrieval.sequence = [two_candidate_result()]
    legacy_deps, _ = make_deps(taxonomy, Settings(), retrieval=legacy_retrieval)
    legacy = await AgentFacade(legacy_deps).run(request)

    native_retrieval = FakeRetrieval()
    native_retrieval.sequence = [two_candidate_result()]
    native_deps, _ = make_deps(taxonomy, Settings(), retrieval=native_retrieval)
    native_deps.graph_checkpointer = MemorySaver()
    native_result = await AgentFacade(native_deps).start(request, AgentExecutionContext())

    assert native_result.response is not None
    legacy_payload = _without_runtime_ids(legacy.model_dump(mode="json"))
    native_payload = _without_runtime_ids(native_result.response.model_dump(mode="json"))
    assert native_payload == legacy_payload
