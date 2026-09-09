"""检索后需求资格校验（RAG 方案 §8.4）。

这里不把召回分数当成资格判断，也不从标题 token 猜测属性语义。只有同一
Offer 的结构化字段或原始属性字段能证明要求时才返回 ``satisfied``；缺失
证据返回 ``unknown``，已知冲突返回 ``conflict``。
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, cast

from shijiajing_agent.contracts import (
    ConstraintSource,
    NormalizedCandidate,
    ShoppingConstraints,
)
from shijiajing_agent.rag_contracts import (
    RequirementMatch,
    RequirementState,
    SemanticRequirement,
)

_NUMBER_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*([a-zA-Z%一-龥]*)\s*$")
_FIELD_ALIASES = {
    "颜色": "color",
    "色": "color",
    "colour": "color",
    "轴体": "switch",
    "轴体类型": "switch",
    "switch_type": "switch",
    "switches": "switch",
    "外壳颜色": "case_color",
    "外壳色": "case_color",
    "case_colour": "case_color",
    "casecolor": "case_color",
}


@dataclass(frozen=True)
class _Fact:
    field: str
    value: Any
    evidence_ref: str
    source: str


@dataclass(frozen=True)
class CandidateQualification:
    matches: list[RequirementMatch]
    eligible: bool


def build_semantic_requirements(
    constraints: ShoppingConstraints,
) -> list[SemanticRequirement]:
    """把当前约束转成请求级需求；字段和值仍来自用户约束。"""
    requirements: list[SemanticRequirement] = []

    def add(
        field: str,
        target: Any,
        *,
        operator: str = "eq",
        user_text: str | None = None,
        source: ConstraintSource = ConstraintSource.DEFAULT,
    ) -> None:
        if (
            target is None
            or target == ""
            or target == []
            or target == {}
            or (
                isinstance(target, dict)
                and not any(value is not None for value in cast(dict[Any, Any], target).values())
            )
        ):
            return
        requirements.append(
            SemanticRequirement(
                requirement_id=f"req:{len(requirements) + 1}:{field}",
                user_text=user_text or f"{field}={target}",
                field=_field_key(field),
                target_value=target,
                operator=operator,  # type: ignore[arg-type]
                hard=source
                in {
                    ConstraintSource.USER_CORRECTION,
                    ConstraintSource.USER_TEXT,
                    ConstraintSource.SELECTED_OPTION,
                },
                source=source.value,
                locked=constraints.is_user_locked(field) if hasattr(constraints, field) else False,
            )
        )

    add("category_id", constraints.category_id.value, source=constraints.category_id.source)
    if not constraints.category_id.value:
        add("category", constraints.category_name.value, source=constraints.category_name.source)
    add("brand", constraints.brand.value, source=constraints.brand.source)
    add("model", constraints.model.value, source=constraints.model.source)
    add(
        "price",
        {
            "min": constraints.min_price.value,
            "max": constraints.max_price.value,
        },
        operator="range",
        source=(
            constraints.max_price.source
            if constraints.max_price.value is not None
            else constraints.min_price.source
        ),
    )
    add(
        "platform",
        constraints.platforms.value,
        operator="in",
        source=constraints.platforms.source,
    )
    add(
        "rating",
        constraints.min_rating.value,
        operator="range",
        source=constraints.min_rating.source,
    )
    add("color", constraints.colors.value, operator="in", source=constraints.colors.source)

    attributes = constraints.attributes.value
    if isinstance(attributes, dict):
        for field, value in cast(dict[Any, Any], attributes).items():
            if value is None:
                continue
            add(str(field), value, source=constraints.attributes.source)
    return requirements


def qualify_candidate(
    candidate: NormalizedCandidate,
    requirements: list[SemanticRequirement],
) -> CandidateQualification:
    """逐需求返回三态结果；硬要求不是 ``satisfied`` 即不能入确认结果。"""
    facts = _facts(candidate)
    matches: list[RequirementMatch] = []
    eligible = True
    for requirement in requirements:
        state, refs, adoption, reason = _evaluate_requirement(requirement, facts)
        matches.append(
            RequirementMatch(
                offer_id=candidate.offer_id,
                requirement_id=requirement.requirement_id,
                state=state,
                evidence_refs=refs,
                adoption=adoption,
                reason=reason,
            )
        )
        if requirement.hard and state is not RequirementState.SATISFIED:
            eligible = False
    return CandidateQualification(matches=matches, eligible=eligible)


def qualify_candidates(
    candidates: list[NormalizedCandidate],
    constraints: ShoppingConstraints,
) -> tuple[list[NormalizedCandidate], list[RequirementMatch], list[str]]:
    """返回合格候选、逐需求诊断和被门禁排除的 Offer ID。"""
    requirements = build_semantic_requirements(constraints)
    eligible: list[NormalizedCandidate] = []
    matches: list[RequirementMatch] = []
    excluded: list[str] = []
    for candidate in candidates:
        result = qualify_candidate(candidate, requirements)
        matches.extend(result.matches)
        if result.eligible:
            eligible.append(candidate)
        else:
            excluded.append(candidate.offer_id)
    return eligible, matches, excluded


def _facts(candidate: NormalizedCandidate) -> list[_Fact]:
    offer = candidate.offer
    facts: list[_Fact] = []
    _add_fact(facts, "category_id", candidate.normalized_category_id, "category_id", "source_fact")
    _add_fact(
        facts,
        "category",
        candidate.normalized_category_concept or candidate.normalized_category_id,
        "category_id",
        "source_fact",
    )
    _add_fact(facts, "brand", candidate.normalized_brand, "brand", "source_fact")
    _add_fact(facts, "model", candidate.normalized_model, "model", "source_fact")
    _add_fact(facts, "price", offer.price, "offer.price", "source_fact")
    _add_fact(facts, "platform", offer.platform, "offer.platform", "source_fact")
    _add_fact(facts, "rating", offer.rating, "offer.rating", "source_fact")

    for group_name, values in (
        ("identity_attributes", candidate.normalized_identity),
        ("variant_attributes", candidate.normalized_variant),
        ("descriptive_attributes", candidate.normalized_descriptive),
    ):
        for key, value in values.items():
            _add_fact(
                facts,
                _field_key(key),
                value,
                f"{group_name}.{key}",
                "source_fact",
            )
    for attribute in offer.raw_attributes:
        _add_fact(
            facts,
            _field_key(attribute.raw_key),
            attribute.raw_value,
            f"raw_attributes.{attribute.attribute_id}.raw_value",
            "raw_attribute",
        )
    return facts


def _add_fact(facts: list[_Fact], field: str, value: Any, evidence_ref: str, source: str) -> None:
    if value is not None and value != "":
        facts.append(_Fact(field, value, evidence_ref, source))


def _evaluate_requirement(
    requirement: SemanticRequirement,
    facts: list[_Fact],
) -> tuple[RequirementState, list[str], str, str]:
    field = _field_key(requirement.field)
    matching = [fact for fact in facts if fact.field == field]
    if not matching:
        return RequirementState.UNKNOWN, [], "unverified", "缺少同一 Offer 的字段证据"

    satisfied: list[_Fact] = []
    conflicts: list[_Fact] = []
    for fact in matching:
        state = _value_state(requirement, fact.value)
        if state is RequirementState.SATISFIED:
            satisfied.append(fact)
        elif state is RequirementState.CONFLICT:
            conflicts.append(fact)
    if satisfied and not conflicts:
        return (
            RequirementState.SATISFIED,
            _refs(satisfied),
            satisfied[0].source,
            "同一 Offer 字段证据满足要求",
        )
    if conflicts:
        return (
            RequirementState.CONFLICT,
            _refs(conflicts),
            conflicts[0].source,
            "同一 Offer 字段证据与要求冲突",
        )
    return RequirementState.UNKNOWN, _refs(matching), matching[0].source, "字段存在但语义证据不足"


def _value_state(
    requirement: SemanticRequirement,
    actual: Any,
) -> RequirementState:
    if requirement.operator == "range":
        return _range_state(requirement, actual)
    if requirement.operator == "in":
        targets = requirement.target_value
        if not isinstance(targets, (list, tuple, set)):
            targets = [targets]
        targets = cast(list[Any] | tuple[Any, ...] | set[Any], targets)
        normalized_actual = _norm(actual)
        normalized_targets = {_norm(item) for item in targets}
        if normalized_actual in normalized_targets:
            return RequirementState.SATISFIED
        return RequirementState.CONFLICT
    target = _norm(requirement.target_value)
    value = _norm(actual)
    if not target or not value:
        return RequirementState.UNKNOWN
    if requirement.operator == "contains":
        return RequirementState.SATISFIED if target in value else RequirementState.CONFLICT
    if requirement.operator == "not_eq":
        return RequirementState.CONFLICT if value == target else RequirementState.SATISFIED
    if value == target:
        return RequirementState.SATISFIED
    # 允许窄值（例如 Cherry MX Red）满足一般的 red switch 要求，
    # 但不允许一般 red 反向证明精确厂商/系列要求。
    if target in value and _field_key(requirement.field) == "switch":
        return RequirementState.SATISFIED
    if value in target and _field_key(requirement.field) == "switch":
        return RequirementState.UNKNOWN
    return RequirementState.CONFLICT


def _range_state(requirement: SemanticRequirement, actual: Any) -> RequirementState:
    number = _number(actual)
    if number is None:
        return RequirementState.UNKNOWN
    target = requirement.target_value
    if isinstance(target, dict):
        target_dict = cast(dict[str, Any], target)
        minimum = _number(target_dict.get("min"))
        maximum = _number(target_dict.get("max"))
        if minimum is not None and number < minimum:
            return RequirementState.CONFLICT
        if maximum is not None and number > maximum:
            return RequirementState.CONFLICT
        return RequirementState.SATISFIED
    minimum = _number(target)
    if minimum is None:
        return RequirementState.UNKNOWN
    return RequirementState.SATISFIED if number >= minimum else RequirementState.CONFLICT


def _number(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if not isinstance(value, str):
        return None
    match = _NUMBER_RE.fullmatch(value)
    return float(match.group(1)) if match else None


def _field_key(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value)).strip().casefold()
    text = re.sub(r"[\s\-/]+", "_", text)
    return _FIELD_ALIASES.get(text, text)


def _norm(value: Any) -> str:
    return unicodedata.normalize("NFKC", str(value)).strip().casefold()


def _refs(facts: list[_Fact]) -> list[str]:
    return list(dict.fromkeys(fact.evidence_ref for fact in facts))[:20]


__all__ = [
    "CandidateQualification",
    "build_semantic_requirements",
    "qualify_candidate",
    "qualify_candidates",
]
