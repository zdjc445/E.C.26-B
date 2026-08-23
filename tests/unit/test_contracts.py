"""Pydantic 协议合法与非法样例（§21.1）。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from shijiajing_agent.contracts import (
    AgentEventRecord,
    AgentRequest,
    ImageContentType,
    ImageRef,
    IntentPatch,
    MemoryApplyMode,
    MemoryMutation,
    MemoryOperation,
    RecognitionCorrection,
    RecognitionResult,
    RetrievalQuery,
)


class TestImageRef:
    def test_valid_https_uri(self):
        ref = ImageRef(
            image_id="i1",
            uri="https://cdn.example.com/a.jpg",
            content_type=ImageContentType.JPEG,
            sha256="a" * 64,
        )
        assert ref.image_id == "i1"

    def test_valid_data_uri(self):
        ref = ImageRef(
            image_id="i1",
            uri="data:image/jpeg;base64,AAAA",
            content_type=ImageContentType.JPEG,
            sha256="a" * 64,
        )
        assert ref.uri.startswith("data:")

    def test_reject_private_scheme(self):
        with pytest.raises(ValidationError):
            ImageRef(
                image_id="i1",
                uri="http://127.0.0.1:8080/x",
                content_type=ImageContentType.JPEG,
                sha256="a" * 64,
            )

    def test_reject_bad_sha(self):
        with pytest.raises(ValidationError):
            ImageRef(
                image_id="i1",
                uri="https://cdn.example.com/a.jpg",
                content_type=ImageContentType.JPEG,
                sha256="zz",
            )

    def test_reject_extra_field(self):
        with pytest.raises(ValidationError):
            ImageRef(
                image_id="i1",
                uri="https://cdn.example.com/a.jpg",
                content_type=ImageContentType.JPEG,
                sha256="a" * 64,
                extra=1,
            )


class TestAgentRequest:
    def test_text_stripped(self):
        req = AgentRequest(session_id="s", request_id="r", text="  索尼耳机  ")
        assert req.text == "索尼耳机"

    def test_blank_text_becomes_none(self):
        req = AgentRequest(session_id="s", request_id="r", text="   ", selected_option_id="opt1")
        assert req.text is None

    def test_at_least_one_input(self):
        with pytest.raises(ValidationError):
            AgentRequest(session_id="s", request_id="r")

    def test_reject_extra_field(self):
        with pytest.raises(ValidationError):
            AgentRequest(session_id="s", request_id="r", text="x", foo=1)


class TestIntentPatch:
    def test_defaults_are_empty_patch(self):
        patch = IntentPatch()
        assert patch.min_price is None
        assert patch.colors is None
        assert patch.clear_fields == []
        assert patch.needs_clarification is False

    def test_min_price_nonnegative(self):
        with pytest.raises(ValidationError):
            IntentPatch(min_price=-1)

    def test_min_rating_range(self):
        with pytest.raises(ValidationError):
            IntentPatch(min_rating=5.5)

    def test_reject_extra_field(self):
        with pytest.raises(ValidationError):
            IntentPatch(fake_field="x")


class TestRecognitionResult:
    def test_reject_extra_field(self):
        with pytest.raises(ValidationError):
            RecognitionResult(recognition_id="r1", hidden_reasoning="secret")

    def test_confidence_range(self):
        with pytest.raises(ValidationError):
            RecognitionResult(recognition_id="r1", overall_confidence=1.5)


class TestRecognitionCorrection:
    def test_valid(self):
        c = RecognitionCorrection(recognition_id="r1", brand="Sony", clear_fields=["model"])
        assert c.brand == "Sony"

    def test_reject_extra_field(self):
        with pytest.raises(ValidationError):
            RecognitionCorrection(recognition_id="r1", bad="x")


class TestRetrievalQuery:
    def test_hard_filters_are_typed(self):
        q = RetrievalQuery(query_text="sony headphone")
        assert q.hard_filters.category_id is None

    def test_reject_extra_field(self):
        with pytest.raises(ValidationError):
            RetrievalQuery(query_text="x", invented="y")


class TestMemoryMutation:
    def test_mutation_id_is_lowercase_sha256_hex(self):
        mutation = MemoryMutation(
            mutation_id="a" * 64,
            operation=MemoryOperation.UPSERT,
            memory_key="max_price",
            value=1000,
            apply_mode=MemoryApplyMode.CONSTRAINT_DEFAULT,
            source_session_id="s1",
            source_request_id="r1",
        )
        assert mutation.mutation_id == "a" * 64

    def test_mutation_id_rejects_non_hex_legacy_shape(self):
        with pytest.raises(ValidationError):
            MemoryMutation(
                mutation_id="g" * 64,
                operation=MemoryOperation.UPSERT,
                memory_key="max_price",
                value=1000,
                apply_mode=MemoryApplyMode.CONSTRAINT_DEFAULT,
                source_session_id="s1",
                source_request_id="r1",
            )


class TestAgentEventRecord:
    @staticmethod
    def _make(payload: dict[str, object]) -> AgentEventRecord:
        return AgentEventRecord(
            event_id="a" * 64,
            session_id="s1",
            request_id="r1",
            turn_id="t1",
            trace_id="tr1",
            agent_name="supervisor",
            event_type="node_completed",
            payload=payload,
            occurred_at="2026-08-22T00:00:00+00:00",
        )

    def test_allows_whitelisted_metadata(self) -> None:
        event = self._make({"prompt_version": "prompt-v1", "token_usage": {"total": 2}})
        assert event.payload["prompt_version"] == "prompt-v1"

    @pytest.mark.parametrize(
        "payload",
        [
            {"prompt": "完整 prompt"},
            {"nested": {"dsn": "postgresql://user:secret@host/db"}},
            {"image": "data:image/jpeg;base64,AAAA"},
            {"user_text": "完整用户文本"},
        ],
    )
    def test_rejects_sensitive_payload(self, payload: dict[str, object]) -> None:
        with pytest.raises(ValidationError, match="事件 payload"):
            self._make(payload)
