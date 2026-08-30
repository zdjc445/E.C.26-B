"""不依赖商品 Taxonomy 的通用规则基线与动态字段采纳。"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field

from shijiajing_agent.contracts import (
    DynamicCanonicalizationItem,
    DynamicFieldStatus,
    EvidenceSpan,
    NormalizedCandidate,
    Offer,
    VerifiedDynamicSchema,
)
from shijiajing_agent.domain.dynamic_schema import (
    evidence_is_grounded,
    schema_attribute,
    source_value,
)
from shijiajing_agent.domain.normalization import canonical_identity_title

_MODEL_SEPARATORS = re.compile(r"[\s\-_/·]+")
_WHITESPACE_RE = re.compile(r"\s+")
_UNIT_PATTERNS: list[tuple[re.Pattern[str], str, float]] = [
    (re.compile(r"^(\d+(?:\.\d+)?)\s*(mm|毫米)$", re.IGNORECASE), "mm", 1.0),
    (re.compile(r"^(\d+(?:\.\d+)?)\s*(cm|厘米)$", re.IGNORECASE), "cm", 1.0),
    (re.compile(r"^(\d+(?:\.\d+)?)\s*(m|米)$", re.IGNORECASE), "m", 1.0),
    (re.compile(r"^(\d+(?:\.\d+)?)\s*(kg|千克|公斤)$", re.IGNORECASE), "kg", 1.0),
    (re.compile(r"^(\d+(?:\.\d+)?)\s*(g|克)$", re.IGNORECASE), "g", 1.0),
    (re.compile(r"^(\d+(?:\.\d+)?)\s*([Ll]|升)$", re.IGNORECASE), "L", 1.0),
    (re.compile(r"^(\d+(?:\.\d+)?)\s*(ml|毫升)$", re.IGNORECASE), "L", 0.001),
    (re.compile(r"^(\d+(?:\.\d+)?)\s*(w|瓦)$", re.IGNORECASE), "W", 1.0),
    (re.compile(r"^(\d+(?:\.\d+)?)\s*(kw|千瓦)$", re.IGNORECASE), "W", 1000.0),
    (re.compile(r"^(\d+(?:\.\d+)?)\s*(h|小时)$", re.IGNORECASE), "h", 1.0),
]


def normalize_open_text(value: str | None) -> str | None:
    if value is None:
        return None
    value = _WHITESPACE_RE.sub(" ", unicodedata.normalize("NFKC", value).strip())
    return value or None


def normalize_open_model(value: str | None) -> str | None:
    value = normalize_open_text(value)
    if value is None:
        return None
    return _MODEL_SEPARATORS.sub(" ", value).strip() or None


def normalize_open_attribute(value: str | None) -> str | None:
    text = normalize_open_text(value)
    if text is None:
        return None
    for pattern, unit, factor in _UNIT_PATTERNS:
        match = pattern.fullmatch(text)
        if match:
            return f"{float(match.group(1)) * factor:g}{unit}"
    return text


def open_text_equal(left: str | None, right: str | None) -> bool:
    a = normalize_open_text(left)
    b = normalize_open_text(right)
    return bool(a and b and a.casefold() == b.casefold())


class GenericNormalizer:
    """跨品类通用规则基线，不维护品牌、品类或属性枚举知识。"""

    version = "generic-v1"

    def normalize_offer(self, offer: Offer) -> NormalizedCandidate:
        category = normalize_open_text(offer.category_id)
        brand = normalize_open_text(offer.brand)
        model = normalize_open_model(offer.model)
        identity = {
            key: value
            for key, raw in offer.identity_attributes.items()
            if (value := normalize_open_attribute(raw)) is not None
        }
        variant = {
            key: value
            for key, raw in offer.variant_attributes.items()
            if (value := normalize_open_attribute(raw)) is not None
        }
        descriptive = {
            key: value
            for key, raw in offer.descriptive_attributes.items()
            if (value := normalize_open_attribute(raw)) is not None
        }
        normalized_title = canonical_identity_title(category, brand, model, identity)
        return NormalizedCandidate(
            offer_id=offer.offer_id,
            offer=offer.model_copy(
                update={"normalized_title": normalized_title or offer.normalized_title}
            ),
            normalized_category_id=category,
            normalized_brand=brand,
            normalized_model=model,
            normalized_identity=identity,
            normalized_variant=variant,
            normalized_descriptive=descriptive,
            normalization_failures=[],
            recall_score=0.0,
        )


@dataclass(frozen=True)
class DynamicFieldDecision:
    field_path: str
    status: DynamicFieldStatus
    reason: str


@dataclass(frozen=True)
class DynamicPatchResult:
    candidate: NormalizedCandidate
    decisions: list[DynamicFieldDecision] = field(default_factory=list[DynamicFieldDecision])

    @property
    def rejected_count(self) -> int:
        return sum(item.status is DynamicFieldStatus.REJECTED for item in self.decisions)

    @property
    def accepted_count(self) -> int:
        return sum(item.status is DynamicFieldStatus.ACCEPTED for item in self.decisions)

    @property
    def descriptive_only_count(self) -> int:
        return sum(item.status is DynamicFieldStatus.DESCRIPTIVE_ONLY for item in self.decisions)


def _evidence_ok(offer: Offer, evidence: EvidenceSpan | None) -> bool:
    return evidence is not None and evidence_is_grounded(offer, evidence)


def _append_failure(failures: list[str], value: str) -> None:
    if value not in failures:
        failures.append(value)


def _core_patch(
    baseline: NormalizedCandidate,
    offer: Offer,
    *,
    proposed: str | None,
    confidence: float | None,
    evidence: EvidenceSpan | None,
    field_name: str,
    normalizer: Callable[[str | None], str | None],
    min_confidence: float,
    failures: list[str],
    decisions: list[DynamicFieldDecision],
) -> str | None:
    current = baseline.normalized_brand if field_name == "brand" else baseline.normalized_model
    if proposed is None:
        return current
    if confidence is None or confidence < min_confidence or not _evidence_ok(offer, evidence):
        _append_failure(failures, f"dynamic_rejected:{field_name}")
        decisions.append(
            DynamicFieldDecision(
                field_name,
                DynamicFieldStatus.REJECTED,
                "missing_or_invalid_evidence",
            )
        )
        return current
    normalized = normalizer(proposed)
    if normalized is None:
        _append_failure(failures, f"dynamic_rejected:{field_name}")
        decisions.append(
            DynamicFieldDecision(field_name, DynamicFieldStatus.REJECTED, "empty_normalized_value")
        )
        return current
    if current is not None and not open_text_equal(current, normalized):
        if (
            evidence is not None
            and evidence.source_path == field_name
            and source_value(offer, evidence.source_path) is not None
        ):
            decisions.append(
                DynamicFieldDecision(
                    field_name,
                    DynamicFieldStatus.ACCEPTED,
                    "structured_surface_normalized",
                )
            )
            return normalized
        _append_failure(failures, f"dynamic_conflict:{field_name}")
        decisions.append(
            DynamicFieldDecision(field_name, DynamicFieldStatus.REJECTED, "structured_source_wins")
        )
        return current
    decisions.append(DynamicFieldDecision(field_name, DynamicFieldStatus.ACCEPTED, "grounded"))
    return current or normalized


def apply_dynamic_patch(
    baseline: NormalizedCandidate,
    item: DynamicCanonicalizationItem,
    schema: VerifiedDynamicSchema,
    offer: Offer,
    *,
    min_confidence: float = 0.80,
    fill_only: bool = False,
) -> DynamicPatchResult:
    """对单条动态 proposal 执行证据、Schema、来源优先级和角色采纳。"""

    candidate = baseline
    failures = list(candidate.normalization_failures)
    decisions: list[DynamicFieldDecision] = []
    if item.offer_id != offer.offer_id or item.offer_id != baseline.offer_id:
        return DynamicPatchResult(
            candidate,
            [
                DynamicFieldDecision(
                    "offer_id",
                    DynamicFieldStatus.REJECTED,
                    "offer_id_mismatch",
                )
            ],
        )

    assignment = next((a for a in schema.assignments if a.offer_id == offer.offer_id), None)
    concept = schema.concept_for_offer(offer.offer_id)
    if (
        assignment is None
        or concept is None
        or item.local_concept_id
        not in {
            None,
            assignment.local_concept_id,
        }
    ):
        if item.local_concept_id is not None:
            decisions.append(
                DynamicFieldDecision(
                    "local_concept_id",
                    DynamicFieldStatus.REJECTED,
                    "schema_assignment_mismatch",
                )
            )
        item = item.model_copy(update={"fields": []})

    category_concept = candidate.normalized_category_concept
    category_confidence = candidate.dynamic_category_confidence
    if item.category_concept is not None:
        if (
            item.category_confidence is None
            or item.category_confidence < min_confidence
            or not _evidence_ok(offer, item.category_evidence)
        ):
            _append_failure(failures, "dynamic_rejected:category_concept")
            decisions.append(
                DynamicFieldDecision(
                    "category_concept",
                    DynamicFieldStatus.REJECTED,
                    "missing_or_invalid_evidence",
                )
            )
        elif category_concept and not open_text_equal(category_concept, item.category_concept):
            _append_failure(failures, "dynamic_conflict:category_concept")
            decisions.append(
                DynamicFieldDecision(
                    "category_concept",
                    DynamicFieldStatus.REJECTED,
                    "concept_conflict",
                )
            )
        else:
            category_concept = normalize_open_text(item.category_concept)
            category_confidence = item.category_confidence or 0.0
            decisions.append(
                DynamicFieldDecision("category_concept", DynamicFieldStatus.ACCEPTED, "grounded")
            )

    brand = _core_patch(
        candidate,
        offer,
        proposed=item.brand,
        confidence=item.brand_confidence,
        evidence=item.brand_evidence,
        field_name="brand",
        normalizer=normalize_open_text,
        min_confidence=min_confidence,
        failures=failures,
        decisions=decisions,
    )
    model = _core_patch(
        candidate,
        offer,
        proposed=item.model,
        confidence=item.model_confidence,
        evidence=item.model_evidence,
        field_name="model",
        normalizer=normalize_open_model,
        min_confidence=min_confidence,
        failures=failures,
        decisions=decisions,
    )

    identity = dict(candidate.normalized_identity)
    variant = dict(candidate.normalized_variant)
    descriptive = dict(candidate.normalized_descriptive)
    for field_item in item.fields:
        field_name = f"field:{field_item.canonical_key}"
        attribute = schema_attribute(schema, offer.offer_id, field_item.canonical_key)
        if (
            attribute is None
            or not _evidence_ok(offer, field_item.evidence)
            or field_item.confidence < min_confidence
        ):
            _append_failure(failures, f"dynamic_rejected:{field_item.canonical_key}")
            decisions.append(
                DynamicFieldDecision(
                    field_name,
                    DynamicFieldStatus.REJECTED,
                    "schema_or_evidence_invalid",
                )
            )
            continue
        value = normalize_open_attribute(field_item.canonical_value)
        if value is None:
            _append_failure(failures, f"dynamic_rejected:{field_item.canonical_key}")
            decisions.append(
                DynamicFieldDecision(
                    field_name,
                    DynamicFieldStatus.REJECTED,
                    "empty_normalized_value",
                )
            )
            continue
        target: dict[str, str]
        if attribute.role == "identity" and field_item.role == "identity":
            target = identity
            status = DynamicFieldStatus.ACCEPTED
        elif attribute.role == "variant" and field_item.role == "variant":
            target = variant
            status = DynamicFieldStatus.ACCEPTED
        else:
            target = descriptive
            status = DynamicFieldStatus.DESCRIPTIVE_ONLY
        previous = target.get(field_item.canonical_key)
        if previous is not None and not open_text_equal(previous, value):
            _append_failure(failures, f"dynamic_conflict:{field_item.canonical_key}")
            decisions.append(
                DynamicFieldDecision(
                    field_name,
                    DynamicFieldStatus.REJECTED,
                    "structured_source_wins",
                )
            )
            continue
        if fill_only and previous is not None:
            decisions.append(DynamicFieldDecision(field_name, status, "existing_value_preserved"))
            continue
        target[field_item.canonical_key] = previous or value
        decisions.append(DynamicFieldDecision(field_name, status, "grounded"))

    for unresolved in item.unresolved_fields:
        decisions.append(
            DynamicFieldDecision(
                f"unresolved:{unresolved}", DynamicFieldStatus.UNRESOLVED, "model_unresolved"
            )
        )

    normalized_title = canonical_identity_title(
        category_concept or candidate.normalized_category_id,
        brand,
        model,
        identity,
    )
    dynamic_variant_keys = (
        [attribute.canonical_key for attribute in concept.attributes if attribute.role == "variant"]
        if concept is not None
        else []
    )
    updated = candidate.model_copy(
        update={
            "offer": offer.model_copy(
                update={"normalized_title": normalized_title or offer.normalized_title}
            ),
            "normalized_brand": brand,
            "normalized_model": model,
            "normalized_identity": identity,
            "normalized_variant": variant,
            "normalized_descriptive": descriptive,
            "normalized_category_concept": category_concept,
            "dynamic_category_confidence": category_confidence,
            "dynamic_schema_id": schema.schema_id,
            "dynamic_variant_keys": sorted(set(dynamic_variant_keys)),
            "dynamic_field_statuses": {
                decision.field_path: decision.status for decision in decisions
            },
            "normalization_failures": list(dict.fromkeys(failures)),
        }
    )
    return DynamicPatchResult(updated, decisions)
