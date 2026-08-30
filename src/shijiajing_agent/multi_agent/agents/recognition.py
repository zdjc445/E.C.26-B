"""Recognition Agent：图片识别、用户修正与字段归一化。"""

from __future__ import annotations

from time import perf_counter
from typing import Any, TypedDict

from shijiajing_agent.contracts import (
    AgentResultV2,
    AgentTaskError,
    AgentTaskUsage,
    AgentTaskV2,
    NodeStatus,
    RecognitionResult,
    RecognitionTaskInput,
    RecognitionTaskOutput,
    SpecialistAgentName,
)
from shijiajing_agent.domain.normalization import TaxonomyNormalizer
from shijiajing_agent.multi_agent.agents.base import fixed_error, result_for, task_usage
from shijiajing_agent.ports.dependencies import AgentDependenciesPort


class RecognitionAgentState(TypedDict, total=False):
    task_id: str
    image_id: str | None
    correction_applied: bool
    repair_count: int
    recognition: RecognitionResult | None
    error: AgentTaskError | None
    usage: AgentTaskUsage


class RecognitionAgent:
    name = SpecialistAgentName.RECOGNITION

    def __init__(self, deps: AgentDependenciesPort) -> None:
        self._deps = deps

    async def execute(self, task: AgentTaskV2) -> AgentResultV2:
        start = perf_counter()
        data = task.input
        if not isinstance(data, RecognitionTaskInput):
            return result_for(
                task,
                status=NodeStatus.FAILED,
                error=fixed_error("INVALID_TASK_INPUT", "Recognition input 类型不匹配"),
            )
        try:
            recognition = data.previous_recognition
            if data.correction is not None:
                if (
                    recognition is None
                    or data.correction.recognition_id != recognition.recognition_id
                ):
                    raise ValueError("修正必须指向当前任务授权的 recognition_id")
                update: dict[str, Any] = {
                    "category_id": recognition.category_id,
                    "category_name": recognition.category_name,
                    "brand": recognition.brand,
                    "model": recognition.model,
                    "attributes": dict(recognition.attributes),
                    "field_confidences": dict(recognition.field_confidences),
                }
                attributes = dict(recognition.attributes)
                field_confidences = dict(recognition.field_confidences)
                update["attributes"] = attributes
                update["field_confidences"] = field_confidences
                for field in data.correction.clear_fields:
                    if field in {"category_id", "category_name", "brand", "model"}:
                        update[field] = None
                    if field == "attributes":
                        attributes.clear()
                for field in ("category_id", "brand", "model"):
                    value = getattr(data.correction, field)
                    if value is not None:
                        update[field] = value
                        field_confidences[field] = 1.0
                for key, value in data.correction.attributes.items():
                    if value is None:
                        attributes.pop(key, None)
                    else:
                        attributes[key] = value
                recognition = recognition.model_copy(update=update)
            elif data.image is not None:
                recognition = await self._deps.vision.recognize(data.image, self._deps.taxonomy)
            else:
                raise ValueError("Recognition 任务缺少 image 或 correction")
            normalized = TaxonomyNormalizer(self._deps.taxonomy).normalize_recognition(
                category_id=recognition.category_id,
                brand=recognition.brand,
                model=recognition.model,
                attributes=recognition.attributes,
            )
            recognition = recognition.model_copy(update=normalized)
            review = (
                recognition.overall_confidence < self._deps.settings.recognition_review_threshold
            )
            output = RecognitionTaskOutput(
                recognition=recognition,
                review_recommended=review,
            )
            return result_for(
                task,
                status=NodeStatus.SUCCESS,
                output=output,
                usage=task_usage(start, calls=0 if data.correction else 1),
            )
        except Exception:
            return result_for(
                task,
                status=NodeStatus.FALLBACK,
                output=RecognitionTaskOutput(
                    recognition=None,
                    fallback_reason="recognition_unavailable",
                ),
                error=fixed_error("RECOGNITION_UNAVAILABLE", "图片识别不可用，可继续文字理解"),
                usage=task_usage(start, calls=1),
            )


__all__ = ["RecognitionAgent", "RecognitionAgentState"]
