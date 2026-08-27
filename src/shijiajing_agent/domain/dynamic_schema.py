"""动态局部商品 Schema 的确定性校验。

模型只能提出 proposal；本模块负责证据 grounding、Offer 范围、概念/属性一致性、
角色降级以及服务端 schema_id。这里不保存跨请求商品知识，也不依赖具体模型或缓存适配器。
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from shijiajing_agent.contracts import (
    DynamicSchemaProposal,
    EvidenceSpan,
    Offer,
    OfferConceptAssignment,
    VerifiedDynamicAttribute,
    VerifiedDynamicConcept,
    VerifiedDynamicSchema,
)

_WHITESPACE_RE = re.compile(r"\s+")
_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


class DynamicSchemaValidationError(ValueError):
    """整个动态 Schema proposal 不安全时的固定领域错误。"""


@dataclass(frozen=True)
class DynamicSchemaValidationConfig:
    concept_min_confidence: float = 0.90
    role_min_confidence: float = 0.90
    role_min_support: int = 2
    max_concepts: int = 16
    max_attributes_per_concept: int = 64


def normalize_evidence_text(value: str) -> str:
    """用于证据连续出现检查的 NFKC、大小写和空白规范化。"""

    return _WHITESPACE_RE.sub(" ", unicodedata.normalize("NFKC", value).casefold()).strip()


def source_value(offer: Offer, source_path: str) -> str | None:
    """读取允许的 Offer 原始字段；未知路径一律返回 None。"""

    if source_path == "title":
        return offer.title
    if source_path == "category_id":
        return offer.category_id
    if source_path == "brand":
        return offer.brand
    if source_path == "model":
        return offer.model
    prefix, _, key = source_path.partition(".")
    if prefix == "identity_attributes":
        return offer.identity_attributes.get(key)
    if prefix == "variant_attributes":
        return offer.variant_attributes.get(key)
    if prefix == "descriptive_attributes":
        return offer.descriptive_attributes.get(key)
    return None


def evidence_is_grounded(offer: Offer, evidence: EvidenceSpan) -> bool:
    """验证证据属于同一 Offer 且 raw_value 在指定原文字段中连续出现。"""

    if evidence.offer_id != offer.offer_id:
        return False
    raw_source = source_value(offer, evidence.source_path)
    if raw_source is None:
        return False
    needle = normalize_evidence_text(evidence.raw_value)
    haystack = normalize_evidence_text(raw_source)
    if not needle or needle not in haystack:
        return False
    if evidence.start is not None or evidence.end is not None:
        start = evidence.start if evidence.start is not None else 0
        end = evidence.end if evidence.end is not None else len(raw_source)
        if start > end or end > len(raw_source):
            return False
        if normalize_evidence_text(raw_source[start:end]) != needle:
            return False
    return True


def _config_from(
    config: DynamicSchemaValidationConfig | None,
    *,
    concept_min_confidence: float | None,
    role_min_confidence: float | None,
    role_min_support: int | None,
    max_concepts: int | None,
    max_attributes_per_concept: int | None,
) -> DynamicSchemaValidationConfig:
    base = config or DynamicSchemaValidationConfig()
    return DynamicSchemaValidationConfig(
        concept_min_confidence=(
            base.concept_min_confidence
            if concept_min_confidence is None
            else concept_min_confidence
        ),
        role_min_confidence=(
            base.role_min_confidence if role_min_confidence is None else role_min_confidence
        ),
        role_min_support=base.role_min_support if role_min_support is None else role_min_support,
        max_concepts=base.max_concepts if max_concepts is None else max_concepts,
        max_attributes_per_concept=(
            base.max_attributes_per_concept
            if max_attributes_per_concept is None
            else max_attributes_per_concept
        ),
    )


def _valid_evidence(
    evidence: list[EvidenceSpan], offers_by_id: dict[str, Offer]
) -> list[EvidenceSpan]:
    return [
        item
        for item in evidence
        if item.offer_id in offers_by_id and evidence_is_grounded(offers_by_id[item.offer_id], item)
    ]


def _support_ids(evidence: list[EvidenceSpan]) -> list[str]:
    return sorted({item.offer_id for item in evidence})


def _alias_key(value: str) -> str:
    return normalize_evidence_text(value)


def _verified_concept_payload(concept: VerifiedDynamicConcept) -> dict[str, Any]:
    return concept.model_dump(mode="json")


def _verified_schema_hash(
    concepts: list[VerifiedDynamicConcept],
    assignments: list[OfferConceptAssignment],
    input_offer_ids: list[str],
) -> str:
    payload = {
        "concepts": [_verified_concept_payload(item) for item in concepts],
        "assignments": [item.model_dump(mode="json") for item in assignments],
        "input_offer_ids": sorted(input_offer_ids),
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def verify_dynamic_schema(
    proposal: DynamicSchemaProposal,
    offers: list[Offer],
    *,
    config: DynamicSchemaValidationConfig | None = None,
    concept_min_confidence: float | None = None,
    role_min_confidence: float | None = None,
    role_min_support: int | None = None,
    max_concepts: int | None = None,
    max_attributes_per_concept: int | None = None,
) -> VerifiedDynamicSchema:
    """校验并生成服务端签名的动态 Schema。

    任一结构性越界、重复 assignment、证据伪造或 alias 冲突都会拒绝整份 proposal。
    单个属性的角色置信度/支持度不足则安全降为 ``descriptive``。
    """

    cfg = _config_from(
        config,
        concept_min_confidence=concept_min_confidence,
        role_min_confidence=role_min_confidence,
        role_min_support=role_min_support,
        max_concepts=max_concepts,
        max_attributes_per_concept=max_attributes_per_concept,
    )
    if len(offers) != len({offer.offer_id for offer in offers}):
        raise DynamicSchemaValidationError("输入 Offer 的 offer_id 必须唯一")
    offers_by_id = {offer.offer_id: offer for offer in offers}
    if len(proposal.concepts) > cfg.max_concepts:
        raise DynamicSchemaValidationError("动态 Schema 概念数超出上限")

    concept_ids = [concept.local_concept_id for concept in proposal.concepts]
    if len(concept_ids) != len(set(concept_ids)):
        raise DynamicSchemaValidationError("local_concept_id 不能重复")
    concepts_by_id = {concept.local_concept_id: concept for concept in proposal.concepts}

    assignments: list[OfferConceptAssignment] = []
    assigned_ids: set[str] = set()
    for assignment in proposal.assignments:
        if assignment.offer_id not in offers_by_id:
            raise DynamicSchemaValidationError("Schema assignment 引用了输入集合外的 offer_id")
        if assignment.offer_id in assigned_ids:
            raise DynamicSchemaValidationError("一个 Offer 最多只能有一个 concept assignment")
        assigned_ids.add(assignment.offer_id)
        if assignment.local_concept_id not in concepts_by_id:
            raise DynamicSchemaValidationError("Schema assignment 引用了不存在的 concept")
        if assignment.confidence < cfg.concept_min_confidence:
            continue
        if not _valid_evidence(assignment.evidence, offers_by_id):
            continue
        assignments.append(assignment)

    aliases_seen: dict[str, str] = {}
    verified_concepts: list[VerifiedDynamicConcept] = []
    valid_concepts: set[str] = set()
    for concept in proposal.concepts:
        concept_evidence = _valid_evidence(concept.evidence, offers_by_id)
        if concept.label_confidence < cfg.concept_min_confidence or not concept_evidence:
            continue
        if len(concept.attributes) > cfg.max_attributes_per_concept:
            raise DynamicSchemaValidationError("动态 Schema 属性数超出上限")
        keys: set[str] = set()
        attrs: list[VerifiedDynamicAttribute] = []
        for attribute in concept.attributes:
            if not _KEY_RE.fullmatch(attribute.canonical_key):
                raise DynamicSchemaValidationError("canonical_key 格式非法")
            if attribute.canonical_key in keys:
                raise DynamicSchemaValidationError("同一 concept 内 canonical_key 不能重复")
            keys.add(attribute.canonical_key)
            attr_evidence = _valid_evidence(attribute.evidence, offers_by_id)
            if not attr_evidence:
                continue
            support_ids = _support_ids(attr_evidence)
            alias_values = [attribute.canonical_key, *attribute.aliases]
            for alias in alias_values:
                normalized_alias = _alias_key(alias)
                if not normalized_alias:
                    continue
                previous = aliases_seen.get(normalized_alias)
                if previous is not None and previous != attribute.canonical_key:
                    raise DynamicSchemaValidationError("同一 alias 不能映射到多个 canonical_key")
                aliases_seen[normalized_alias] = attribute.canonical_key
            role = attribute.role
            if (
                attribute.role_confidence < cfg.role_min_confidence
                or len(support_ids) < cfg.role_min_support
            ):
                role = "descriptive"
            attrs.append(
                VerifiedDynamicAttribute(
                    canonical_key=attribute.canonical_key,
                    aliases=list(dict.fromkeys(attribute.aliases)),
                    role=role,
                    value_kind=attribute.value_kind,
                    unit_family=attribute.unit_family,
                    role_confidence=attribute.role_confidence,
                    support_offer_ids=support_ids,
                    evidence=attr_evidence,
                )
            )
        verified_concepts.append(
            VerifiedDynamicConcept(
                local_concept_id=concept.local_concept_id,
                canonical_label=concept.canonical_label,
                label_confidence=concept.label_confidence,
                evidence=concept_evidence,
                attributes=attrs,
            )
        )
        valid_concepts.add(concept.local_concept_id)

    assignments = [
        item for item in assignments if item.local_concept_id in valid_concepts
    ]
    input_offer_ids = [offer.offer_id for offer in offers]
    schema_id = _verified_schema_hash(verified_concepts, assignments, input_offer_ids)
    return VerifiedDynamicSchema(
        schema_id=schema_id,
        concepts=verified_concepts,
        assignments=assignments,
        input_offer_ids=sorted(input_offer_ids),
    )


def schema_id_for(schema: VerifiedDynamicSchema) -> str:
    """重新计算 Schema ID，用于缓存命中后的完整性复核。"""

    return _verified_schema_hash(schema.concepts, schema.assignments, schema.input_offer_ids)


def schema_has_drift(left: VerifiedDynamicSchema, right: VerifiedDynamicSchema) -> bool:
    """比较两个已验证 Schema 的规范语义是否漂移。"""

    return schema_id_for(left) != schema_id_for(right)


def schema_attribute(
    schema: VerifiedDynamicSchema, offer_id: str, canonical_key: str
) -> VerifiedDynamicAttribute | None:
    concept = schema.concept_for_offer(offer_id)
    if concept is None:
        return None
    return next(
        (attribute for attribute in concept.attributes if attribute.canonical_key == canonical_key),
        None,
    )
