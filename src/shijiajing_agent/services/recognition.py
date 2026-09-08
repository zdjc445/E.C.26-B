"""识别服务：把 VLM 与用户修正收敛成可复用的业务入口。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from shijiajing_agent.contracts import ImageRef, RecognitionCorrection, RecognitionResult
from shijiajing_agent.domain.normalization import TaxonomyNormalizer
from shijiajing_agent.domain.taxonomy import Taxonomy
from shijiajing_agent.ports.models import VisionModelPort


@dataclass(frozen=True)
class RecognitionOutcome:
    recognition: RecognitionResult | None
    review_recommended: bool = False
    model_calls: int = 0
    fallback_reason: str | None = None


class RecognitionService:
    """识别与修正共用同一套 taxonomy 归一化逻辑。"""

    def __init__(
        self, vision: VisionModelPort, taxonomy: Taxonomy, review_threshold: float
    ) -> None:
        self._vision = vision
        self._taxonomy = taxonomy
        self._review_threshold = review_threshold

    async def run(
        self,
        *,
        image: ImageRef | None = None,
        correction: RecognitionCorrection | None = None,
        previous: RecognitionResult | None = None,
    ) -> RecognitionOutcome:
        try:
            if correction is not None:
                if previous is None or correction.recognition_id != previous.recognition_id:
                    raise ValueError("修正必须指向当前会话最新的 recognition_id")
                recognition = self._apply(previous, correction)
                model_calls = 0
            elif image is not None:
                recognition = await self._vision.recognize(image, self._taxonomy)
                model_calls = 1
            else:
                return RecognitionOutcome(None, fallback_reason="no_recognition_input")
            recognition = self._normalize(recognition)
            return RecognitionOutcome(
                recognition,
                review_recommended=recognition.overall_confidence < self._review_threshold,
                model_calls=model_calls,
            )
        except Exception:
            return RecognitionOutcome(
                None,
                model_calls=0 if correction is not None else 1,
                fallback_reason="recognition_unavailable",
            )

    async def recognize(self, image: ImageRef) -> RecognitionResult:
        outcome = await self.run(image=image)
        if outcome.recognition is None:
            raise RuntimeError(outcome.fallback_reason or "recognition_unavailable")
        return outcome.recognition

    async def apply_correction(
        self, previous: RecognitionResult, correction: RecognitionCorrection
    ) -> RecognitionResult:
        outcome = await self.run(previous=previous, correction=correction)
        if outcome.recognition is None:
            raise ValueError(outcome.fallback_reason or "correction_failed")
        return outcome.recognition

    def _normalize(self, recognition: RecognitionResult) -> RecognitionResult:
        normalized = TaxonomyNormalizer(self._taxonomy).normalize_recognition(
            category_id=recognition.category_id,
            brand=recognition.brand,
            model=recognition.model,
            attributes=recognition.attributes,
        )
        return recognition.model_copy(update=normalized)

    @staticmethod
    def _apply(
        recognition: RecognitionResult, correction: RecognitionCorrection
    ) -> RecognitionResult:
        attributes = dict(recognition.attributes)
        confidences = dict(recognition.field_confidences)
        update: dict[str, Any] = {
            "category_id": recognition.category_id,
            "category_name": recognition.category_name,
            "brand": recognition.brand,
            "model": recognition.model,
            "attributes": attributes,
            "field_confidences": confidences,
        }
        for field in correction.clear_fields:
            if field in {"category_id", "category_name", "brand", "model"}:
                update[field] = None
            elif field == "attributes":
                attributes.clear()
        for field in ("category_id", "brand", "model"):
            value = getattr(correction, field)
            if value is not None:
                update[field] = value
                confidences[field] = 1.0
        for key, value in correction.attributes.items():
            if value is None:
                attributes.pop(key, None)
            else:
                attributes[key] = value
        return recognition.model_copy(update=update)


__all__ = ["RecognitionOutcome", "RecognitionService"]
