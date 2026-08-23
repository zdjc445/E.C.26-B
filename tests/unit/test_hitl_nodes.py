"""四类 HITL 节点的触发与专用恢复契约测试。"""

from __future__ import annotations

from types import SimpleNamespace

from shijiajing_agent.config import Settings
from shijiajing_agent.contracts import (
    AgentRequest,
    MemoryApplyMode,
    MemoryMutation,
    MemoryOperation,
    RecognitionResult,
)
from shijiajing_agent.domain.normalization import TaxonomyNormalizer
from shijiajing_agent.nodes.hitl_nodes import (
    make_memory_confirmation_interrupt_node,
    make_recognition_review_interrupt_node,
    make_same_item_review_interrupt_node,
)
from shijiajing_agent.state import new_state
from tests.unit.conftest import offer


def make_state(*, recognition: RecognitionResult | None = None):
    state = new_state(
        schema_version="1.1",
        session_id="s1",
        request_id="r1",
        turn_id="t1",
        trace_id="tr1",
        current_request=AgentRequest(session_id="s1", request_id="r1", text="找耳机"),
    )
    state["recognition"] = recognition
    state["recognition_id"] = recognition.recognition_id if recognition else None
    return state


def test_recognition_review_triggers_for_unresolved_fields(monkeypatch, mini_taxonomy) -> None:
    recognition = RecognitionResult(
        recognition_id="rec-1",
        category_id=None,
        overall_confidence=0.99,
        unresolved_fields=["category_id"],
    )
    monkeypatch.setattr(
        "shijiajing_agent.nodes.hitl_nodes.interrupt", lambda _: {"action": "approve"}
    )
    node = make_recognition_review_interrupt_node(
        SimpleNamespace(settings=Settings(recognition_review_threshold=0.7), taxonomy=mini_taxonomy)
    )

    result = node(make_state(recognition=recognition))

    assert result["next_action"] == "recognition_review_approved"
    assert result["resume_consumed"] is True


def test_recognition_review_edit_normalizes_and_resolves_fields(monkeypatch, mini_taxonomy) -> None:
    recognition = RecognitionResult(
        recognition_id="rec-1",
        category_id="headphone",
        category_name="耳机",
        brand=None,
        model="wh-1000xm5",
        attributes={},
        overall_confidence=0.4,
        unresolved_fields=["brand", "noise_cancellation"],
    )
    answer = {
        "action": "edit",
        "correction": {
            "recognition_id": "rec-1",
            "brand": "索尼",
            "attributes": {"noise_cancellation": "主动降噪"},
        },
    }
    monkeypatch.setattr("shijiajing_agent.nodes.hitl_nodes.interrupt", lambda _: answer)
    node = make_recognition_review_interrupt_node(
        SimpleNamespace(settings=Settings(recognition_review_threshold=0.7), taxonomy=mini_taxonomy)
    )

    result = node(make_state(recognition=recognition))

    updated = result["recognition"]
    assert updated.brand == "Sony"
    assert updated.model == "WH 1000XM5"
    assert updated.attributes == {"noise_cancellation": "主动降噪"}
    assert updated.unresolved_fields == []


def test_same_item_review_split_rebuilds_clusters(monkeypatch, mini_taxonomy) -> None:
    normalized = [
        TaxonomyNormalizer(mini_taxonomy).normalize_offer(offer("o1")),
        TaxonomyNormalizer(mini_taxonomy).normalize_offer(offer("o2")),
    ]
    state = make_state()
    state["normalized_candidates"] = normalized
    state["spu_clusters"] = [[0, 1]]
    state["same_item_review_pairs"] = [
        {"offer_a_id": "o1", "offer_b_id": "o2", "same_item_score": 0.7}
    ]
    monkeypatch.setattr(
        "shijiajing_agent.nodes.hitl_nodes.interrupt", lambda _: {"action": "split"}
    )

    result = make_same_item_review_interrupt_node(None)(state)

    assert result["spu_clusters"] == [[0], [1]]
    assert result["next_action"] == "same_item_review_split"
    assert result["resume_consumed"] is True


def test_memory_confirmation_reject_clears_pending_mutations(monkeypatch) -> None:
    state = make_state()
    state["pending_memory_mutations"] = [
        MemoryMutation(
            mutation_id="a" * 64,
            operation=MemoryOperation.UPSERT,
            memory_key="max_price",
            value=1000,
            scope_key="global",
            apply_mode=MemoryApplyMode.CONSTRAINT_DEFAULT,
            source_session_id="s1",
            source_request_id="r1",
        )
    ]
    monkeypatch.setattr(
        "shijiajing_agent.nodes.hitl_nodes.interrupt", lambda _: {"action": "reject"}
    )

    result = make_memory_confirmation_interrupt_node(None)(state)

    assert result["pending_memory_mutations"] == []
    assert result["next_action"] == "memory_confirmation_rejected"
    assert result["resume_consumed"] is True
