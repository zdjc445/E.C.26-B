"""开放域商品归一化应用服务。

运行时只保留动态路径：通用规则基线 → 局部 Schema 发现与校验 → 按 Schema
归一化 → 字段级确定性采纳。模型或缓存异常时按批回退通用规则基线。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from shijiajing_agent.contracts import (
    DynamicCanonicalizationBatch,
    DynamicFieldStatus,
    NormalizedCandidate,
    Offer,
    VerifiedDynamicSchema,
)
from shijiajing_agent.domain.cache_policy import safe_get, safe_set, versioned_key
from shijiajing_agent.domain.dynamic_schema import (
    DynamicSchemaValidationConfig,
    schema_id_for,
    verify_dynamic_schema,
)
from shijiajing_agent.domain.open_world_normalization import (
    DynamicPatchResult,
    GenericNormalizer,
    apply_dynamic_patch,
)
from shijiajing_agent.ports.cache import VersionedCachePort
from shijiajing_agent.ports.models import (
    DynamicProductCanonicalizationPort,
    DynamicSchemaInductionPort,
)
from shijiajing_agent.ports.observability import MetricsPort


@dataclass(frozen=True)
class ProductCanonicalizationRun:
    candidates: list[NormalizedCandidate]
    model_calls: int = 0
    cache_hits: int = 0
    fallback_batches: int = 0
    rejected_fields: int = 0
    notices: list[str] | None = None
    verified_schema: VerifiedDynamicSchema | None = None
    schema_id: str | None = None
    accepted_fields: int = 0
    descriptive_only_fields: int = 0
    rejected_reasons: dict[str, int] | None = None


async def canonicalize_offers(
    offers: list[Offer],
    schema_inducer: DynamicSchemaInductionPort | None,
    canonicalizer: DynamicProductCanonicalizationPort | None,
    *,
    schema_batch_size: int = 60,
    canonicalization_batch_size: int = 20,
    concept_min_confidence: float = 0.90,
    role_min_confidence: float = 0.90,
    role_min_support: int = 2,
    max_concepts: int = 16,
    max_attributes_per_concept: int = 64,
    field_min_confidence: float = 0.80,
    cache: VersionedCachePort | None = None,
    cache_ttl_seconds: int = 604_800,
    metrics: MetricsPort | None = None,
) -> ProductCanonicalizationRun:
    """执行动态两阶段归一化；任一批失败时仅回退该批。"""

    baseline = [GenericNormalizer().normalize_offer(offer) for offer in offers]
    if not offers or schema_inducer is None or canonicalizer is None:
        if offers:
            _metric(
                metrics,
                "open_world_candidate_total",
                len(offers),
                labels={"decision": "baseline"},
            )
        return ProductCanonicalizationRun(
            candidates=baseline,
            notices=["动态商品 Schema 端口不可用，已使用通用规则基线"] if offers else [],
            fallback_batches=1 if offers else 0,
        )

    merged: list[NormalizedCandidate] = []
    total_model_calls = 0
    total_cache_hits = 0
    fallback_batches = 0
    accepted_fields = 0
    descriptive_fields = 0
    rejected_fields = 0
    rejected_reasons: dict[str, int] = {}
    notices: list[str] = []
    verified_schemas: list[VerifiedDynamicSchema] = []

    schema_size = max(1, schema_batch_size)
    canonical_size = max(1, canonicalization_batch_size)
    for start in range(0, len(offers), schema_size):
        batch_offers = offers[start : start + schema_size]
        schema_key = versioned_key(
            [_cache_offer_payload(offer) for offer in batch_offers],
            {
                "schema_inducer": getattr(schema_inducer, "version", "unknown"),
                "schema_policy": "dynamic-schema-v1",
                "rules": GenericNormalizer.version,
            },
        )
        schema: VerifiedDynamicSchema | None = None
        cached_schema = await safe_get(cache, "dynamic_schema", schema_key, metrics=metrics)
        if cached_schema is not None:
            try:
                candidate_schema = VerifiedDynamicSchema.model_validate(cached_schema)
                if (
                    candidate_schema.input_offer_ids
                    == sorted(offer.offer_id for offer in batch_offers)
                    and schema_id_for(candidate_schema) == candidate_schema.schema_id
                ):
                    schema = candidate_schema
                    total_cache_hits += 1
                    _metric(metrics, "dynamic_schema_cache_hit_total")
            except Exception:
                schema = None
        if schema is None:
            try:
                proposal = await schema_inducer.induce_schema(batch_offers)
                schema = verify_dynamic_schema(
                    proposal,
                    batch_offers,
                    config=DynamicSchemaValidationConfig(
                        concept_min_confidence=concept_min_confidence,
                        role_min_confidence=role_min_confidence,
                        role_min_support=role_min_support,
                        max_concepts=max_concepts,
                        max_attributes_per_concept=max_attributes_per_concept,
                    ),
                )
                demoted_count = _count_role_demotions(proposal, schema)
                if demoted_count:
                    _metric(
                        metrics,
                        "dynamic_schema_role_demoted_total",
                        demoted_count,
                        labels={"reason": "confidence_or_support"},
                    )
                total_model_calls += 1
                _metric(metrics, "dynamic_schema_model_batch_total")
                await safe_set(
                    cache,
                    "dynamic_schema",
                    schema_key,
                    schema.model_dump(mode="json"),
                    cache_ttl_seconds,
                    metrics=metrics,
                )
            except Exception:
                fallback_batches += 1
                _metric(metrics, "dynamic_schema_fallback_total")
                _metric(
                    metrics,
                    "dynamic_schema_rejected_total",
                    labels={"reason": "validation_or_model_failure"},
                )
                _metric(
                    metrics,
                    "open_world_candidate_total",
                    len(batch_offers),
                    labels={"decision": "baseline"},
                )
                notices.append("动态 Schema proposal 非法或模型不可用，已使用通用规则基线")
                merged.extend(baseline[start : start + len(batch_offers)])
                continue
        verified_schemas.append(schema)

        for canonical_start in range(0, len(batch_offers), canonical_size):
            canonical_offers = batch_offers[canonical_start : canonical_start + canonical_size]
            canonical_cache_key = versioned_key(
                [_cache_offer_payload(offer) for offer in canonical_offers],
                {
                    "schema_id": schema.schema_id,
                    "canonicalizer": getattr(canonicalizer, "version", "unknown"),
                    "rules": GenericNormalizer.version,
                    "policy": "dynamic-canonicalization-v1",
                },
            )
            result: DynamicCanonicalizationBatch | None = None
            cached_result = await safe_get(
                cache,
                "dynamic_canonicalization",
                canonical_cache_key,
                metrics=metrics,
            )
            if cached_result is not None:
                try:
                    candidate_result = DynamicCanonicalizationBatch.model_validate(cached_result)
                    expected_ids = {offer.offer_id for offer in canonical_offers}
                    if candidate_result.schema_id == schema.schema_id and all(
                        item.offer_id in expected_ids for item in candidate_result.items
                    ):
                        result = candidate_result
                        total_cache_hits += 1
                        _metric(metrics, "dynamic_canonicalization_cache_hit_total")
                except Exception:
                    result = None
            if result is None:
                try:
                    result = await canonicalizer.canonicalize_dynamic(canonical_offers, schema)
                    if result.schema_id != schema.schema_id:
                        raise ValueError("dynamic canonicalization schema_id 不匹配")
                    expected_ids = {offer.offer_id for offer in canonical_offers}
                    if any(item.offer_id not in expected_ids for item in result.items):
                        raise ValueError("dynamic canonicalization 返回了输入集合外的 offer_id")
                    total_model_calls += 1
                    _metric(metrics, "dynamic_canonicalization_model_batch_total")
                    await safe_set(
                        cache,
                        "dynamic_canonicalization",
                        canonical_cache_key,
                        result.model_dump(mode="json"),
                        cache_ttl_seconds,
                        metrics=metrics,
                    )
                except Exception:
                    result = None
            if result is None:
                fallback_batches += 1
                _metric(metrics, "dynamic_schema_fallback_total")
                _metric(
                    metrics,
                    "open_world_candidate_total",
                    len(canonical_offers),
                    labels={"decision": "baseline"},
                )
                notices.append("动态商品归一化批次模型不可用，已使用通用规则基线")
                merged.extend(
                    baseline[
                        start + canonical_start : start + canonical_start + len(canonical_offers)
                    ]
                )
                continue
            items = {item.offer_id: item for item in result.items}
            for offset, offer in enumerate(canonical_offers):
                base = baseline[start + canonical_start + offset]
                item = items.get(offer.offer_id)
                if item is None:
                    merged.append(base)
                    notices.append(f"商品 {offer.offer_id} 缺少动态归一化结果，已使用通用规则基线")
                    _metric(metrics, "dynamic_canonicalization_missing_item_total")
                    _metric(
                        metrics,
                        "open_world_candidate_total",
                        labels={"decision": "baseline"},
                    )
                    continue
                patch: DynamicPatchResult = apply_dynamic_patch(
                    base,
                    item,
                    schema,
                    offer,
                    min_confidence=field_min_confidence,
                )
                merged.append(patch.candidate)
                accepted_fields += patch.accepted_count
                descriptive_fields += patch.descriptive_only_count
                rejected_fields += patch.rejected_count
                for decision in patch.decisions:
                    if decision.status is DynamicFieldStatus.REJECTED:
                        rejected_reasons[decision.reason] = (
                            rejected_reasons.get(decision.reason, 0) + 1
                        )
                _metric(
                    metrics,
                    "open_world_candidate_total",
                    labels={
                        "decision": (
                            "patched"
                            if patch.accepted_count or patch.descriptive_only_count
                            else "baseline"
                        )
                    },
                )
                for decision in patch.decisions:
                    _metric(
                        metrics,
                        "dynamic_canonicalization_field_total",
                        labels={
                            "status": decision.status.value,
                            "field_kind": _dynamic_field_kind(decision.field_path),
                        },
                    )

    if rejected_fields:
        notices.append(f"{rejected_fields} 个动态字段因证据、冲突或角色不一致被拒绝")
    schema_id = verified_schemas[0].schema_id if len(verified_schemas) == 1 else None
    return ProductCanonicalizationRun(
        candidates=merged,
        model_calls=total_model_calls,
        cache_hits=total_cache_hits,
        fallback_batches=fallback_batches,
        rejected_fields=rejected_fields,
        notices=notices,
        verified_schema=verified_schemas[0] if len(verified_schemas) == 1 else None,
        schema_id=schema_id,
        accepted_fields=accepted_fields,
        descriptive_only_fields=descriptive_fields,
        rejected_reasons=rejected_reasons,
    )


def _cache_offer_payload(offer: Offer) -> dict[str, Any]:
    return {
        "offer_id": offer.offer_id,
        "platform": offer.platform,
        "source_product_id": offer.source_product_id,
        "source_updated_at": offer.source_updated_at,
        "title": offer.title,
        "category_id": offer.category_id,
        "brand": offer.brand,
        "model": offer.model,
        "identity_attributes": offer.identity_attributes,
        "variant_attributes": offer.variant_attributes,
        "descriptive_attributes": offer.descriptive_attributes,
    }


def _metric(
    metrics: MetricsPort | None,
    name: str,
    value: int = 1,
    *,
    labels: dict[str, str] | None = None,
) -> None:
    if metrics is None:
        return
    try:
        metrics.inc(name, labels=labels, value=float(value))
    except Exception:
        return


def _dynamic_field_kind(field_path: str) -> str:
    if field_path == "category_concept":
        return "category"
    if field_path in {"brand", "model"}:
        return "core"
    if field_path.startswith("unresolved:"):
        return "unresolved"
    return "attribute"


def _count_role_demotions(proposal: Any, verified: VerifiedDynamicSchema) -> int:
    verified_by_concept = {concept.local_concept_id: concept for concept in verified.concepts}
    count = 0
    for proposed_concept in proposal.concepts:
        verified_concept = verified_by_concept.get(proposed_concept.local_concept_id)
        if verified_concept is None:
            continue
        verified_by_key = {
            attribute.canonical_key: attribute for attribute in verified_concept.attributes
        }
        for proposed_attribute in proposed_concept.attributes:
            attribute = verified_by_key.get(proposed_attribute.canonical_key)
            if (
                attribute is not None
                and proposed_attribute.role in {"identity", "variant"}
                and attribute.role == "descriptive"
            ):
                count += 1
    return count
