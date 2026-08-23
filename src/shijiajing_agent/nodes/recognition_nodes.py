"""识别节点：VLM 识别、用户修正、识别标准化。

失败策略（§18）：
- VLM 失败且有文字品类 → 跳过图片结论继续；无文字 → 下游澄清/失败。
- 修正的 ``recognition_id`` 与当前最新识别不一致 → 直接拒绝。
"""

from __future__ import annotations

from typing import Any

from shijiajing_agent.contracts import AgentRequest, RecognitionResult
from shijiajing_agent.domain.cache_policy import safe_get, safe_set, versioned_key
from shijiajing_agent.domain.normalization import TaxonomyNormalizer
from shijiajing_agent.errors import ModelOutputInvalidError, VisionUnavailableError
from shijiajing_agent.nodes.node_support import record_cache_event, set_dirty, timed
from shijiajing_agent.persistence_safety import is_redacted_image_ref
from shijiajing_agent.ports.dependencies import AgentDependenciesPort
from shijiajing_agent.ports.models import VisionModelPort
from shijiajing_agent.state import AgentState, ErrorRecord

# 识别语义校验（§11.2）：
# category 必须存在于 taxonomy；attributes 键必须属于品类 schema；
# field_confidences 必须覆盖所有非空识别字段；brand/model 不得只出现在解释中。
_DOWNSTREAM_DIRTY = (
    "normalization_dirty",
    "query_dirty",
    "retrieval_dirty",
    "matching_dirty",
    "ranking_dirty",
    "explanation_dirty",
)


def _validate_recognition(result: RecognitionResult, taxonomy: Any) -> list[str]:
    errors: list[str] = []
    if result.category_id is not None and taxonomy.resolve_category(result.category_id)[0] is None:
        errors.append(f"category_id {result.category_id!r} 不在 taxonomy 中")
    for key in result.attributes:
        if result.category_id and not taxonomy.validate_attribute(
            result.category_id, key, result.attributes[key]
        ):
            errors.append(f"attribute {key!r} 不属于品类 schema")
    for field_name in ("category_id", "brand", "model"):
        if (
            getattr(result, field_name) is not None
            and result.field_confidences.get(field_name) is None
        ):
            errors.append(f"field_confidences 缺少 {field_name}")
    return errors


def make_recognize_image_node(deps: AgentDependenciesPort) -> Any:
    """VLM 商品识别（§11.2）。失败时置空识别并记录错误，不阻断下游。"""

    vision: VisionModelPort = deps.vision

    @timed("recognize_image")
    async def recognize_image_node(state: AgentState) -> dict[str, Any]:
        image = state.get("image_ref")
        if image is None:
            return {}
        errors: list[ErrorRecord] = list(state.get("errors") or [])
        notices = list(state.get("notices") or [])
        if is_redacted_image_ref(image):
            return {
                "recognition": None,
                "next_action": "recognition_failed",
                "errors": [
                    *errors,
                    {
                        "node_name": "recognize_image",
                        "error_code": "IMAGE_UNAVAILABLE",
                        "message": "持久化图片引用已脱敏，不能重新读取原始图片",
                    },
                ],
                "notices": [*notices, "原始图片不可恢复，请使用原始请求重试"],
                **set_dirty(state, *_DOWNSTREAM_DIRTY),
            }
        try:
            cache_key = versioned_key(
                {"image_sha256": image.sha256},
                {
                    "model": deps.settings.ark_vision_model,
                    "prompt": "v1",
                    "taxonomy": deps.taxonomy.taxonomy_version,
                },
            )
            cached = await safe_get(deps.cache, "vision", cache_key, metrics=deps.metrics)
            cached_result = None
            if isinstance(cached, dict) and isinstance(cached.get("recognition"), dict):
                try:
                    candidate = RecognitionResult.model_validate(cached["recognition"])
                    if not _validate_recognition(candidate, deps.taxonomy):
                        cached_result = candidate
                except Exception:
                    cached_result = None
            await record_cache_event(
                deps,
                state,
                node_name="recognize_image",
                namespace="vision",
                cache_key=cache_key,
                hit=cached_result is not None,
            )
            if cached_result is not None:
                result = cached_result
                return {
                    "recognition": result,
                    "recognition_history": [
                        *list(state.get("recognition_history") or []),
                        result,
                    ],
                    "recognition_id": result.recognition_id,
                    "next_action": "recognition_done",
                    **set_dirty(state, *_DOWNSTREAM_DIRTY),
                }
            result = await vision.recognize(image, deps.taxonomy)
            semantic_errors = _validate_recognition(result, deps.taxonomy)
            if semantic_errors:
                raise ModelOutputInvalidError(
                    "识别结果未通过语义校验: " + "; ".join(semantic_errors)
                )
            await safe_set(
                deps.cache,
                "vision",
                cache_key,
                {"recognition": result.model_dump(mode="json")},
                deps.settings.vision_cache_ttl_seconds,
                metrics=deps.metrics,
            )
            return {
                "recognition": result,
                "recognition_history": [*list(state.get("recognition_history") or []), result],
                "recognition_id": result.recognition_id,
                "next_action": "recognition_done",
                **set_dirty(state, *_DOWNSTREAM_DIRTY),
            }
        except (VisionUnavailableError, ModelOutputInvalidError) as exc:
            code = getattr(exc, "code", None) or "MODEL_OUTPUT_INVALID"
            return {
                "recognition": None,
                "next_action": "recognition_failed",
                "errors": [
                    *errors,
                    {
                        "node_name": "recognize_image",
                        "error_code": str(code),
                        "message": exc.user_message,
                    },
                ],
                "notices": [*notices, "图片识别不可用，已按文字信息继续"],
                **set_dirty(state, *_DOWNSTREAM_DIRTY),
            }
        except Exception:
            return {
                "recognition": None,
                "next_action": "recognition_failed",
                "errors": [
                    *errors,
                    {
                        "node_name": "recognize_image",
                        "error_code": "INTERNAL_ERROR",
                        "message": "图片识别执行失败",
                    },
                ],
                "notices": [*notices, "图片识别失败，已按文字信息继续"],
                **set_dirty(state, *_DOWNSTREAM_DIRTY),
            }

    return recognize_image_node


def make_apply_correction_node(deps: AgentDependenciesPort) -> Any:
    """用户修正：recognition_id 不一致直接拒绝。"""

    @timed("apply_correction")
    async def apply_correction_node(state: AgentState) -> dict[str, Any]:
        req: AgentRequest = state["current_request"]
        correction = req.correction
        if correction is None:
            return {}
        latest_id = state.get("recognition_id")
        if latest_id is None or correction.recognition_id != latest_id:
            raise ModelOutputInvalidError(
                f"修正的 recognition_id {correction.recognition_id!r} 与当前识别不一致"
            )
        recognition = state.get("recognition")
        if recognition is None:
            raise ModelOutputInvalidError("当前会话没有可供修正的识别结果")
        attributes = dict(recognition.attributes)
        if "attributes" in correction.clear_fields:
            attributes.clear()
        for key, value in correction.attributes.items():
            if value is None:
                attributes.pop(key, None)
            else:
                attributes[key] = value
        corrected_fields = set(correction.clear_fields)
        update: dict[str, Any] = {
            "category_id": None if "category_id" in corrected_fields else recognition.category_id,
            "category_name": (
                None if "category_name" in corrected_fields else recognition.category_name
            ),
            "brand": None if "brand" in corrected_fields else recognition.brand,
            "model": None if "model" in corrected_fields else recognition.model,
            "attributes": attributes,
        }
        if correction.category_id is not None:
            update["category_id"] = correction.category_id
        if correction.brand is not None:
            update["brand"] = correction.brand
        if correction.model is not None:
            update["model"] = correction.model
        field_confidences = dict(recognition.field_confidences)
        for field_name in ("category_id", "brand", "model"):
            if field_name in corrected_fields:
                field_confidences.pop(field_name, None)
            elif update[field_name] != getattr(recognition, field_name):
                field_confidences[field_name] = 1.0
        update["field_confidences"] = field_confidences
        corrected = recognition.model_copy(update=update)
        return {
            "recognition": corrected,
            "recognition_history": [*list(state.get("recognition_history") or []), corrected],
            "next_action": "correction_applied",
            **set_dirty(state, *_DOWNSTREAM_DIRTY),
        }

    return apply_correction_node


def make_normalize_recognition_node(deps: AgentDependenciesPort) -> Any:
    """识别结果标准化：未知值置空并记录 notice。"""

    @timed("normalize_recognition")
    async def normalize_recognition_node(state: AgentState) -> dict[str, Any]:
        recognition = state.get("recognition")
        if recognition is None:
            return {}
        normalized = TaxonomyNormalizer(deps.taxonomy).normalize_recognition(
            category_id=recognition.category_id,
            brand=recognition.brand,
            model=recognition.model,
            attributes=recognition.attributes,
        )
        notices = list(state.get("notices") or [])
        if normalized["category_id"] is None and recognition.category_id:
            notices.append(f"识别品类 {recognition.category_id} 不在 taxonomy 中，已忽略")
        normalized_recognition = recognition.model_copy(update=normalized)
        return {
            "recognition": normalized_recognition,
            "notices": notices,
            "next_action": "normalized",
        }

    return normalize_recognition_node
