"""意图节点：意图抽取、约束合并、约束校验与失效标记（方案 §11.3、§8、§10.1）。

- ``parse_intent``：模型只输出当前轮 patch；失败/非法时规则解析（§11.3）。
- ``merge_constraints``：按 §8.1 优先级合并多来源。
- ``validate_constraints``：检测冲突、校验 taxonomy 属性，并按失效矩阵（§10.1）
  计算本轮 dirty_flags。
"""

from __future__ import annotations

from typing import Any, cast

from shijiajing_agent.contracts import (
    AgentRequest,
    IntentPatch,
    ShoppingConstraints,
    SourcedValue,
)
from shijiajing_agent.domain.cache_policy import safe_get, safe_set, versioned_key
from shijiajing_agent.domain.constraints import ConstraintMerger
from shijiajing_agent.domain.intent_rules import RuleIntentParser
from shijiajing_agent.domain.memory_policy import apply_memory_defaults
from shijiajing_agent.errors import ModelOutputInvalidError
from shijiajing_agent.nodes.node_support import record_cache_event, timed
from shijiajing_agent.ports.dependencies import AgentDependenciesPort
from shijiajing_agent.ports.models import IntentModelPort
from shijiajing_agent.state import AgentState

_DIRTY_ALL_DOWNSTREAM = (
    "normalization_dirty",
    "query_dirty",
    "retrieval_dirty",
    "matching_dirty",
    "ranking_dirty",
    "explanation_dirty",
)
_DIRTY_QUERY_DOWNSTREAM = (
    "query_dirty",
    "retrieval_dirty",
    "matching_dirty",
    "ranking_dirty",
    "explanation_dirty",
)
_DIRTY_RANKING = ("ranking_dirty", "explanation_dirty")


def make_parse_intent_node(deps: AgentDependenciesPort) -> Any:
    """文本意图抽取（§11.3）。模型失败或输出非法 → 规则解析。"""

    intent_model: IntentModelPort = deps.intent

    @timed("parse_intent")
    async def parse_intent_node(state: AgentState) -> dict[str, Any]:
        req: AgentRequest = state["current_request"]
        text = req.text
        if not text:
            return {"intent_patch": None, "next_action": "no_intent"}
        prev = state.get("effective_constraints") or (
            (state.get("previous_state") or {}).get("effective_constraints")
        )
        patch: IntentPatch | None = None
        fallback_used = False
        cache_key = versioned_key(
            {
                "text": text,
                "previous_constraints": (
                    prev.model_dump(mode="json") if isinstance(prev, ShoppingConstraints) else None
                ),
            },
            {
                "model": deps.settings.ark_text_model,
                "prompt": "v1",
                "taxonomy": deps.taxonomy.taxonomy_version,
            },
        )
        try:
            cached = await safe_get(deps.cache, "intent", cache_key, metrics=deps.metrics)
            cached_patch = None
            if isinstance(cached, dict) and isinstance(cached.get("intent_patch"), dict):
                try:
                    cached_patch = IntentPatch.model_validate(cached["intent_patch"])
                except Exception:
                    cached_patch = None
            await record_cache_event(
                deps,
                state,
                node_name="parse_intent",
                namespace="intent",
                cache_key=cache_key,
                hit=cached_patch is not None,
            )
            if cached_patch is not None:
                patch = cached_patch
            else:
                patch = await intent_model.extract_intent(text, prev, deps.taxonomy)
                await safe_set(
                    deps.cache,
                    "intent",
                    cache_key,
                    {"intent_patch": patch.model_dump(mode="json")},
                    deps.settings.intent_cache_ttl_seconds,
                    metrics=deps.metrics,
                )
        except ModelOutputInvalidError:
            fallback_used = True
        except Exception:
            fallback_used = True
        if patch is None:
            parser = RuleIntentParser(deps.taxonomy)
            patch = parser.parse(text)
        delta: dict[str, Any] = {
            "intent_patch": patch,
            "next_action": "intent_done",
            "notices": list(state.get("notices") or []),
        }
        if fallback_used:
            delta["notices"].append("意图模型不可用，已使用规则解析")
            delta["fallbacks"] = [
                *list(state.get("fallbacks") or []),
                {
                    "node_name": "parse_intent",
                    "reason": "model_failed",
                    "fallback_provider": "rules",
                },
            ]
        return delta

    return parse_intent_node


def make_merge_constraints_node(deps: AgentDependenciesPort) -> Any:
    """合并多来源约束（§8.1），并计算 dirty_flags（§10.1 失效矩阵）。"""

    @timed("merge_constraints")
    async def merge_constraints_node(state: AgentState) -> dict[str, Any]:
        req: AgentRequest = state["current_request"]
        prev = state.get("previous_state")
        prev_constraints = (
            (prev.get("effective_constraints") if prev else None)
            or state.get("effective_constraints")
            or None
        )
        vision = state.get("recognition")
        patch = state.get("intent_patch")
        has_new_image = state.get("image_ref") is not None
        new_subject = has_new_image

        merger = ConstraintMerger(deps.taxonomy)
        result = merger.merge(
            prev=prev_constraints,
            vision=vision,
            intent=patch,
            correction=req.correction,
            new_subject=new_subject,
            turn_id=str(state.get("turn_id", "")),
            subject_id=state.get("subject_id"),
        )
        effective_constraints = result.constraints
        if state.get("memory_context"):
            effective_constraints = apply_memory_defaults(
                effective_constraints, list(state.get("memory_context") or [])
            )
        return {
            "effective_constraints": effective_constraints,
            "conflicts": [c.__dict__ for c in result.conflicts],
            "notices": list(state.get("notices") or []) + list(result.notices),
            "next_action": "merged",
            **_compute_dirty(
                state, prev_constraints, result.constraints, has_new_image, req.correction
            ),
        }

    return merge_constraints_node


def _field_pair(
    obj: dict[str, Any] | ShoppingConstraints | None, name: str
) -> tuple[Any, Any] | None:
    """提取约束字段的 (value, source)：支持 pydantic 对象与 dict 两种形态。"""
    if obj is None:
        return None
    raw: Any = obj.get(name) if isinstance(obj, dict) else getattr(obj, name, None)
    if isinstance(raw, SourcedValue):
        return raw.value, raw.source
    if isinstance(raw, dict):
        raw_dict = cast(dict[str, Any], raw)
        return raw_dict.get("value"), raw_dict.get("source")
    if raw is None:
        return None
    return raw, None


def _fields_changed(prev: Any, merged: Any) -> set[str]:
    """比较 prev 与 merged 中每个约束字段的 (value, source)。"""
    changed: set[str] = set()
    names = (
        "category_id",
        "category_name",
        "brand",
        "model",
        "min_price",
        "max_price",
        "colors",
        "platforms",
        "min_rating",
        "sort_by",
        "preferences",
        "attributes",
    )
    for name in names:
        a = _field_pair(prev, name)
        b = _field_pair(merged, name)
        if a != b:
            changed.add(name)
    return changed


def _compute_dirty(
    state: AgentState,
    prev: Any,
    merged: Any,
    has_new_image: bool,
    correction: Any,
) -> dict[str, dict[str, bool]]:
    """§10.1 失效矩阵：按本轮变化标记必须重跑的节点。"""
    from shijiajing_agent.nodes.node_support import set_dirty

    changed = _fields_changed(prev, merged)
    if prev is None or has_new_image:
        return set_dirty(
            state,
            "recognition_dirty",
            "normalization_dirty",
            "intent_dirty",
            "query_dirty",
            "retrieval_dirty",
            "matching_dirty",
            "ranking_dirty",
            "explanation_dirty",
        )
    dirty: list[str] = []
    if correction is not None:
        # 用户修正：跳过 VLM，重跑标准化及下游（§10.1）
        dirty += [
            "normalization_dirty",
            *[
                "query_dirty",
                "retrieval_dirty",
                "matching_dirty",
                "ranking_dirty",
                "explanation_dirty",
            ],
        ]
    if changed & {
        "min_price",
        "max_price",
        "platforms",
        "min_rating",
        "colors",
        "brand",
        "model",
        "category_id",
        "attributes",
    }:
        dirty += list(_DIRTY_QUERY_DOWNSTREAM)
    if changed & {"sort_by", "preferences"}:
        dirty += list(_DIRTY_RANKING)
    if not changed and correction is None:
        dirty += ["explanation_dirty"]  # 只要求解释当前结果
    result = set_dirty(state, *dirty)
    # 未变化的阶段明确保持干净（LangGraph 替换语义下重放原值）
    return result


def make_validate_constraints_node(deps: AgentDependenciesPort) -> Any:
    """约束校验：冲突进入澄清；属性必须属于品类 schema（§8.3）。"""

    @timed("validate_constraints")
    async def validate_constraints_node(state: AgentState) -> dict[str, Any]:
        constraints = state.get("effective_constraints")
        conflicts = list(state.get("conflicts") or [])
        if constraints is None:
            return {"next_action": "no_constraints", "conflicts": conflicts}
        # 属性 schema 校验在 ConstraintMerger 内已完成；此处只决定路由
        missing_category = constraints.category_id.value is None
        next_action = "clarify" if (conflicts or missing_category) else "retrievable"
        return {"next_action": next_action}

    return validate_constraints_node
