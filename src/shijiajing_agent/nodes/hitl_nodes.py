"""LangGraph interrupt 节点及四类专用 resume 校验。"""

from __future__ import annotations

import hashlib
from typing import Any, cast

from langgraph.types import interrupt

from shijiajing_agent.contracts import (
    AgentInterrupt,
    ClarificationResume,
    InterruptKind,
    MatchPair,
    MemoryConfirmationResume,
    RecognitionReviewResume,
    SameItemReviewResume,
)
from shijiajing_agent.domain.normalization import TaxonomyNormalizer
from shijiajing_agent.ports.dependencies import AgentDependenciesPort
from shijiajing_agent.state import AgentState


def _next_interrupt_generation(state: AgentState) -> int:
    current = state.get("interrupt_generation", 0)
    if current < 0:
        raise ValueError("interrupt_generation 必须是非负整数")
    return current + 1


def _interrupt_id(state: AgentState, kind: InterruptKind, node_name: str, generation: int) -> str:
    request = state["current_request"]
    raw = "|".join(
        (
            request.session_id,
            request.request_id,
            str(state.get("turn_id") or ""),
            kind.value,
            node_name,
            str(generation),
        )
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _pause(
    state: AgentState,
    *,
    kind: InterruptKind,
    node_name: str,
    generation: int,
    prompt: str,
    payload: dict[str, Any],
) -> AgentInterrupt:
    request = state["current_request"]
    return AgentInterrupt(
        interrupt_id=_interrupt_id(state, kind, node_name, generation),
        session_id=request.session_id,
        request_id=request.request_id,
        turn_id=str(state.get("turn_id") or ""),
        trace_id=str(state.get("trace_id") or ""),
        kind=kind,
        prompt=prompt,
        payload=payload,
    )


def make_clarification_interrupt_node(deps: AgentDependenciesPort) -> Any:
    del deps

    def clarification_interrupt_node(state: AgentState) -> dict[str, Any]:
        clarification = state.get("clarification")
        generation = _next_interrupt_generation(state)
        interrupt_payload = _pause(
            state,
            kind=InterruptKind.CLARIFICATION,
            node_name="clarification_interrupt",
            generation=generation,
            prompt=clarification.question if clarification is not None else "请补充信息。",
            payload={
                "question_id": clarification.question_id if clarification is not None else None,
                "options": [
                    item.model_dump(mode="json")
                    for item in (clarification.options if clarification else [])
                ],
            },
        )
        resumed = interrupt(interrupt_payload.model_dump(mode="json"))
        if not isinstance(resumed, dict):
            return {
                "active_interrupt": interrupt_payload,
                "resume_consumed": False,
                "interrupt_generation": generation,
            }
        answer = ClarificationResume.model_validate(resumed)
        request = state["current_request"]
        if answer.action == "answer":
            updated_request = request.model_copy(update={"text": answer.text})
        else:
            selected = answer.option_id or ""
            option = next(
                (
                    item
                    for item in (clarification.options if clarification else [])
                    if item.option_id == selected
                ),
                None,
            )
            updated_request = request.model_copy(
                update={
                    "selected_option_id": selected,
                    "text": option.label if option else selected,
                }
            )
        return {
            "current_request": updated_request,
            "active_interrupt": None,
            "resume_consumed": True,
            "interrupt_generation": generation,
            "next_action": "clarification_resumed",
        }

    return clarification_interrupt_node


def make_recognition_review_interrupt_node(deps: AgentDependenciesPort) -> Any:
    def recognition_review_interrupt_node(state: AgentState) -> dict[str, Any]:
        recognition = state.get("recognition")
        if recognition is None:
            return {"next_action": "recognition_review_skipped"}
        threshold = deps.settings.recognition_review_threshold
        requires_review = (
            recognition.category_id is None
            or bool(recognition.unresolved_fields)
            or recognition.overall_confidence < threshold
        )
        if not requires_review:
            return {"next_action": "recognition_review_skipped"}
        generation = _next_interrupt_generation(state)
        interrupt_payload = _pause(
            state,
            kind=InterruptKind.RECOGNITION_REVIEW,
            node_name="recognition_review_interrupt",
            generation=generation,
            prompt="图片识别置信度较低，请确认或修正识别结果。",
            payload={"recognition": recognition.model_dump(mode="json"), "threshold": threshold},
        )
        resumed = interrupt(interrupt_payload.model_dump(mode="json"))
        if not isinstance(resumed, dict):
            return {
                "active_interrupt": interrupt_payload,
                "resume_consumed": False,
                "interrupt_generation": generation,
            }
        answer = RecognitionReviewResume.model_validate(resumed)
        if answer.action == "reject":
            return {
                "recognition": None,
                "recognition_id": None,
                "active_interrupt": None,
                "resume_consumed": True,
                "interrupt_generation": generation,
                "next_action": "recognition_review_rejected",
            }
        if answer.action == "edit":
            correction = answer.correction
            if correction is None or correction.recognition_id != recognition.recognition_id:
                raise ValueError("识别 review 的 correction 必须匹配当前 recognition_id")
            clear_fields = set(correction.clear_fields)
            attributes = dict(recognition.attributes)
            if "attributes" in clear_fields:
                attributes.clear()
            for key, value in correction.attributes.items():
                if value is None:
                    attributes.pop(key, None)
                else:
                    attributes[key] = value
            category_id = None if "category_id" in clear_fields else recognition.category_id
            brand = None if "brand" in clear_fields else recognition.brand
            model = None if "model" in clear_fields else recognition.model
            if correction.category_id is not None:
                category_id = correction.category_id
            if correction.brand is not None:
                brand = correction.brand
            if correction.model is not None:
                model = correction.model
            updated = recognition.model_copy(
                update={
                    "category_id": category_id,
                    "brand": brand,
                    "model": model,
                    "attributes": attributes,
                }
            )
            normalized = TaxonomyNormalizer(deps.taxonomy).normalize_recognition(
                category_id=updated.category_id,
                brand=updated.brand,
                model=updated.model,
                attributes=updated.attributes,
            )
            resolved_fields = set(clear_fields)
            if correction.category_id is not None:
                resolved_fields.add("category_id")
            if correction.brand is not None:
                resolved_fields.add("brand")
            if correction.model is not None:
                resolved_fields.add("model")
            unresolved = [
                field
                for field in recognition.unresolved_fields
                if field not in resolved_fields and field not in correction.attributes
            ]
            updated = updated.model_copy(update={**normalized, "unresolved_fields": unresolved})
            return {
                "recognition": updated,
                "recognition_id": updated.recognition_id,
                "active_interrupt": None,
                "resume_consumed": True,
                "interrupt_generation": generation,
                "next_action": "recognition_review_edited",
            }
        return {
            "active_interrupt": None,
            "resume_consumed": True,
            "interrupt_generation": generation,
            "next_action": "recognition_review_approved",
        }

    return recognition_review_interrupt_node


def make_same_item_review_interrupt_node(deps: AgentDependenciesPort) -> Any:
    del deps

    def same_item_review_interrupt_node(state: AgentState) -> dict[str, Any]:
        raw_pairs = cast(list[Any], state.get("same_item_review_pairs") or [])
        pairs = [MatchPair.model_validate(pair) for pair in raw_pairs]
        if not pairs:
            return {"next_action": "same_item_review_skipped"}
        generation = _next_interrupt_generation(state)
        interrupt_payload = _pause(
            state,
            kind=InterruptKind.SAME_ITEM_REVIEW,
            node_name="same_item_review_interrupt",
            generation=generation,
            prompt="发现可能属于同一商品但证据不足的候选，请确认是否合并。",
            payload={"pairs": [pair.model_dump(mode="json") for pair in pairs]},
        )
        resumed = interrupt(interrupt_payload.model_dump(mode="json"))
        if not isinstance(resumed, dict):
            return {
                "active_interrupt": interrupt_payload,
                "resume_consumed": False,
                "interrupt_generation": generation,
            }
        answer = SameItemReviewResume.model_validate(resumed)
        if answer.action == "accept":
            return {
                "active_interrupt": None,
                "resume_consumed": True,
                "interrupt_generation": generation,
                "same_item_review_pairs": [],
                "next_action": "same_item_review_accepted",
            }
        normalized = list(state.get("normalized_candidates") or [])
        review_ids = {x for pair in pairs for x in (pair.offer_a_id, pair.offer_b_id)}
        rebuilt: list[list[int]] = []
        for cluster in list(state.get("spu_clusters") or []):
            review_indexes = [i for i in cluster if normalized[i].offer_id in review_ids]
            untouched = [i for i in cluster if i not in review_indexes]
            if untouched:
                rebuilt.append(untouched)
            rebuilt.extend([[i] for i in review_indexes])
        return {
            "spu_clusters": rebuilt,
            "same_item_review_pairs": [],
            "active_interrupt": None,
            "resume_consumed": True,
            "interrupt_generation": generation,
            "next_action": "same_item_review_split",
        }

    return same_item_review_interrupt_node


def make_memory_confirmation_interrupt_node(deps: AgentDependenciesPort) -> Any:
    del deps

    def memory_confirmation_interrupt_node(state: AgentState) -> dict[str, Any]:
        mutations = list(state.get("pending_memory_mutations") or [])
        if not mutations:
            return {"next_action": "memory_confirmation_skipped"}
        generation = _next_interrupt_generation(state)
        interrupt_payload = _pause(
            state,
            kind=InterruptKind.MEMORY_CONFIRMATION,
            node_name="memory_confirmation_interrupt",
            generation=generation,
            prompt="本轮请求包含长期偏好变更，是否保存？",
            payload={"mutations": [item.model_dump(mode="json") for item in mutations]},
        )
        resumed = interrupt(interrupt_payload.model_dump(mode="json"))
        if not isinstance(resumed, dict):
            return {
                "active_interrupt": interrupt_payload,
                "resume_consumed": False,
                "interrupt_generation": generation,
            }
        answer = MemoryConfirmationResume.model_validate(resumed)
        return {
            "pending_memory_mutations": mutations if answer.action == "approve" else [],
            "active_interrupt": None,
            "resume_consumed": True,
            "interrupt_generation": generation,
            "next_action": "memory_confirmation_approved"
            if answer.action == "approve"
            else "memory_confirmation_rejected",
        }

    return memory_confirmation_interrupt_node
