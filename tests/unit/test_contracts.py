"""Pydantic 协议合法与非法样例（§21.1）。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from shijiajing_agent.contracts import (
    AgentRequest,
    ImageContentType,
    ImageRef,
    IntentPatch,
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
