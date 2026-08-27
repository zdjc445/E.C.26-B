"""LLM 商品归一化的应用服务与确定性采纳策略。

LLM 只提出带原文证据的字段补丁。平台结构化字段、Taxonomy 与确定性规则拥有
最终决定权；任何模型错误、缓存错误或字段冲突都降级为 ``TaxonomyNormalizer``
的基线结果，不影响后续同款聚类。
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, replace
from typing import Any

from shijiajing_agent.contracts import (
    CanonicalFieldEvidence,
    DynamicCanonicalizationBatch,
    DynamicFieldStatus,
    NormalizedCandidate,
    Offer,
    ProductCanonicalizationBatch,
    ProductCanonicalizationItem,
    VerifiedDynamicSchema,
)
from shijiajing_agent.domain.cache_policy import safe_get, safe_set, versioned_key
from shijiajing_agent.domain.dynamic_schema import (
    DynamicSchemaValidationConfig,
    schema_id_for,
    verify_dynamic_schema,
)
from shijiajing_agent.domain.normalization import (
    TaxonomyNormalizer,
    canonical_identity_title,
)
from shijiajing_agent.domain.open_world_normalization import (
    DynamicPatchResult,
    GenericNormalizer,
    apply_dynamic_patch,
)
from shijiajing_agent.domain.taxonomy import Taxonomy
from shijiajing_agent.ports.cache import VersionedCachePort
from shijiajing_agent.ports.models import (
    DynamicProductCanonicalizationPort,
    DynamicSchemaInductionPort,
    ProductCanonicalizationPort,
)
from shijiajing_agent.ports.observability import MetricsPort

_CACHE_NAMESPACE = "product_canonicalization"
_WHITESPACE_RE = re.compile(r"\s+")


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
    shadow_candidates: list[NormalizedCandidate] | None = None
    shadow_summary: dict[str, int] | None = None


async def canonicalize_offers(
    offers: list[Offer],
    taxonomy: Taxonomy,
    canonicalizer: ProductCanonicalizationPort | None,
    *,
    enabled: bool = True,
    batch_size: int = 20,
    min_confidence: float = 0.75,
    cache: VersionedCachePort | None = None,
    cache_ttl_seconds: int = 604_800,
    metrics: MetricsPort | None = None,
    mode: str = "taxonomy",
    dynamic_schema_inducer: DynamicSchemaInductionPort | None = None,
    dynamic_product_canonicalizer: DynamicProductCanonicalizationPort | None = None,
    dynamic_schema_batch_size: int = 60,
    dynamic_concept_min_confidence: float = 0.90,
    dynamic_role_min_confidence: float = 0.90,
    dynamic_role_min_support: int = 2,
    dynamic_field_min_confidence: float = 0.80,
) -> ProductCanonicalizationRun:
    """规则基线之上批量调用 LLM，并只采纳有证据、可校验的缺失字段。"""

    if mode in {"dynamic", "dynamic_shadow", "hybrid"}:
        if not enabled:
            return await _canonicalize_taxonomy_offers(
                offers,
                taxonomy,
                canonicalizer,
                enabled=False,
                batch_size=batch_size,
                min_confidence=min_confidence,
                cache=cache,
                cache_ttl_seconds=cache_ttl_seconds,
                metrics=metrics,
            )
        dynamic_run = await dynamic_canonicalize_offers(
            offers,
            dynamic_schema_inducer,
            dynamic_product_canonicalizer,
            schema_batch_size=dynamic_schema_batch_size,
            canonicalization_batch_size=batch_size,
            concept_min_confidence=dynamic_concept_min_confidence,
            role_min_confidence=dynamic_role_min_confidence,
            role_min_support=dynamic_role_min_support,
            field_min_confidence=dynamic_field_min_confidence,
            cache=cache,
            cache_ttl_seconds=cache_ttl_seconds,
            metrics=metrics,
        )
        if mode == "dynamic":
            return dynamic_run
        taxonomy_run = await _canonicalize_taxonomy_offers(
            offers,
            taxonomy,
            canonicalizer,
            enabled=enabled,
            batch_size=batch_size,
            min_confidence=min_confidence,
            cache=cache,
            cache_ttl_seconds=cache_ttl_seconds,
            metrics=metrics,
        )
        if mode == "dynamic_shadow":
            shadow_summary = _compare_shadow_candidates(
                taxonomy_run.candidates,
                dynamic_run.candidates,
                taxonomy,
            )
            _metric(
                metrics,
                "dynamic_shadow_candidate_diff_total",
                shadow_summary["changed_candidate_count"],
            )
            _metric(
                metrics,
                "dynamic_shadow_field_diff_total",
                shadow_summary["field_difference_count"],
            )
            return replace(
                taxonomy_run,
                model_calls=taxonomy_run.model_calls + dynamic_run.model_calls,
                cache_hits=taxonomy_run.cache_hits + dynamic_run.cache_hits,
                fallback_batches=taxonomy_run.fallback_batches + dynamic_run.fallback_batches,
                rejected_fields=taxonomy_run.rejected_fields + dynamic_run.rejected_fields,
                verified_schema=dynamic_run.verified_schema,
                schema_id=dynamic_run.schema_id,
                accepted_fields=dynamic_run.accepted_fields,
                descriptive_only_fields=dynamic_run.descriptive_only_fields,
                rejected_reasons=dynamic_run.rejected_reasons,
                shadow_candidates=dynamic_run.candidates,
                shadow_summary=shadow_summary,
                notices=[
                    *(taxonomy_run.notices or []),
                    *(dynamic_run.notices or []),
                    "动态商品归一化运行于 shadow 模式，未改变当前输出",
                ],
            )
        return _merge_hybrid_run(taxonomy_run, dynamic_run)

    return await _canonicalize_taxonomy_offers(
        offers,
        taxonomy,
        canonicalizer,
        enabled=enabled,
        batch_size=batch_size,
        min_confidence=min_confidence,
        cache=cache,
        cache_ttl_seconds=cache_ttl_seconds,
        metrics=metrics,
    )


async def _canonicalize_taxonomy_offers(
    offers: list[Offer],
    taxonomy: Taxonomy,
    canonicalizer: ProductCanonicalizationPort | None,
    *,
    enabled: bool,
    batch_size: int,
    min_confidence: float,
    cache: VersionedCachePort | None,
    cache_ttl_seconds: int,
    metrics: MetricsPort | None,
) -> ProductCanonicalizationRun:
    """原有 Taxonomy 归一化实现，作为显式回滚和 hybrid 基线。"""

    normalizer = TaxonomyNormalizer(taxonomy)
    baseline = [normalizer.normalize_offer(offer) for offer in offers]
    if not offers or not enabled or canonicalizer is None:
        return ProductCanonicalizationRun(candidates=baseline, notices=[])

    proposals: dict[str, ProductCanonicalizationItem] = {}
    model_calls = 0
    cache_hits = 0
    fallback_batches = 0
    missing_results = 0
    notices: list[str] = []
    known_ids = {offer.offer_id for offer in offers}
    canonicalizer_version = getattr(canonicalizer, "version", "unknown")

    for start in range(0, len(offers), max(1, batch_size)):
        batch_offers = offers[start : start + max(1, batch_size)]
        cache_key = versioned_key(
            [_cache_offer_payload(offer) for offer in batch_offers],
            {
                "taxonomy": taxonomy.taxonomy_version,
                "canonicalizer": canonicalizer_version,
            },
        )
        batch: ProductCanonicalizationBatch | None = None
        cached = await safe_get(cache, _CACHE_NAMESPACE, cache_key, metrics=metrics)
        if cached is not None:
            try:
                batch = ProductCanonicalizationBatch.model_validate(cached)
                cache_hits += 1
                _metric(metrics, "product_canonicalization_cache_hit_total")
            except Exception:
                batch = None

        if batch is None:
            try:
                batch = await canonicalizer.canonicalize(batch_offers, taxonomy)
                model_calls += 1
                _metric(metrics, "product_canonicalization_model_batch_total")
                await safe_set(
                    cache,
                    _CACHE_NAMESPACE,
                    cache_key,
                    batch.model_dump(mode="json"),
                    cache_ttl_seconds,
                    metrics=metrics,
                )
            except Exception:
                fallback_batches += 1
                _metric(metrics, "product_canonicalization_fallback_total")
                continue

        expected_ids = {offer.offer_id for offer in batch_offers}
        returned_ids = {item.offer_id for item in batch.items if item.offer_id in expected_ids}
        missing_results += len(expected_ids - returned_ids)
        for item in batch.items:
            if item.offer_id in known_ids and item.offer_id in expected_ids:
                proposals[item.offer_id] = item

    merged: list[NormalizedCandidate] = []
    rejected_fields = 0
    for candidate in baseline:
        proposal = proposals.get(candidate.offer_id)
        if proposal is None:
            merged.append(candidate)
            continue
        updated, rejected = apply_canonicalization_patch(
            candidate,
            proposal,
            taxonomy,
            min_confidence=min_confidence,
        )
        merged.append(updated)
        rejected_fields += rejected

    if fallback_batches:
        notices.append(f"{fallback_batches} 个商品归一化批次模型不可用，已使用规则结果")
    if missing_results:
        notices.append(f"{missing_results} 条商品缺少模型归一化结果，已使用规则结果")
    if rejected_fields:
        notices.append(f"{rejected_fields} 个模型字段因无证据、冲突或不符合 Taxonomy 被拒绝")
        _metric(metrics, "product_canonicalization_rejected_field_total", rejected_fields)

    return ProductCanonicalizationRun(
        candidates=merged,
        model_calls=model_calls,
        cache_hits=cache_hits,
        fallback_batches=fallback_batches,
        rejected_fields=rejected_fields,
        notices=notices,
    )


def _merge_hybrid_run(
    taxonomy_run: ProductCanonicalizationRun,
    dynamic_run: ProductCanonicalizationRun,
) -> ProductCanonicalizationRun:
    """hybrid 只用动态结果补齐 Taxonomy 缺失字段，不覆盖可信结构化事实。"""

    merged: list[NormalizedCandidate] = []
    for static, dynamic in zip(taxonomy_run.candidates, dynamic_run.candidates, strict=False):
        update: dict[str, Any] = {}
        if static.normalized_category_id is None:
            update["normalized_category_concept"] = dynamic.normalized_category_concept
            update["dynamic_category_confidence"] = dynamic.dynamic_category_confidence
        if static.normalized_brand is None:
            update["normalized_brand"] = dynamic.normalized_brand
        if static.normalized_model is None:
            update["normalized_model"] = dynamic.normalized_model
        update["normalized_identity"] = {
            **dynamic.normalized_identity,
            **static.normalized_identity,
        }
        update["normalized_variant"] = {
            **dynamic.normalized_variant,
            **static.normalized_variant,
        }
        update["normalized_descriptive"] = {
            **dynamic.normalized_descriptive,
            **static.normalized_descriptive,
        }
        update["dynamic_schema_id"] = dynamic.dynamic_schema_id
        update["dynamic_variant_keys"] = dynamic.dynamic_variant_keys
        update["dynamic_field_statuses"] = dynamic.dynamic_field_statuses
        merged_candidate = static.model_copy(update=update)
        normalized_title = canonical_identity_title(
            merged_candidate.normalized_category_concept or merged_candidate.normalized_category_id,
            merged_candidate.normalized_brand,
            merged_candidate.normalized_model,
            merged_candidate.normalized_identity,
        )
        if normalized_title:
            merged_candidate = merged_candidate.model_copy(
                update={
                    "offer": merged_candidate.offer.model_copy(
                        update={"normalized_title": normalized_title}
                    )
                }
            )
        merged.append(merged_candidate)
    if len(taxonomy_run.candidates) > len(merged):
        merged.extend(taxonomy_run.candidates[len(merged) :])
    return ProductCanonicalizationRun(
        candidates=merged,
        model_calls=taxonomy_run.model_calls + dynamic_run.model_calls,
        cache_hits=taxonomy_run.cache_hits + dynamic_run.cache_hits,
        fallback_batches=taxonomy_run.fallback_batches + dynamic_run.fallback_batches,
        rejected_fields=taxonomy_run.rejected_fields + dynamic_run.rejected_fields,
        notices=[*(taxonomy_run.notices or []), *(dynamic_run.notices or [])],
        verified_schema=dynamic_run.verified_schema,
        schema_id=dynamic_run.schema_id,
        accepted_fields=dynamic_run.accepted_fields,
        descriptive_only_fields=dynamic_run.descriptive_only_fields,
        rejected_reasons=dynamic_run.rejected_reasons,
    )


def _compare_shadow_candidates(
    static_candidates: list[NormalizedCandidate],
    dynamic_candidates: list[NormalizedCandidate],
    taxonomy: Taxonomy,
) -> dict[str, int]:
    """比较 shadow 字段计数；不把原始商品值写入状态或指标。"""

    static_by_id = {candidate.offer_id: candidate for candidate in static_candidates}
    dynamic_by_id = {candidate.offer_id: candidate for candidate in dynamic_candidates}
    field_counters = (
        "category_fill_count",
        "category_disagreement_count",
        "brand_difference_count",
        "model_difference_count",
        "identity_difference_count",
        "variant_difference_count",
        "descriptive_difference_count",
    )
    summary = {
        "candidate_count": len(static_candidates),
        "aligned_candidate_count": 0,
        "changed_candidate_count": 0,
        "field_difference_count": 0,
        **dict.fromkeys(field_counters, 0),
        "dynamic_only_candidate_count": len(set(dynamic_by_id).difference(static_by_id)),
        "static_only_candidate_count": len(set(static_by_id).difference(dynamic_by_id)),
    }

    for offer_id, static in static_by_id.items():
        dynamic = dynamic_by_id.get(offer_id)
        if dynamic is None:
            continue
        summary["aligned_candidate_count"] += 1
        before = sum(summary[counter] for counter in field_counters)

        static_category = _category_name(static, taxonomy)
        dynamic_category = _shadow_text(dynamic.normalized_category_concept)
        if static.normalized_category_id is None and dynamic_category:
            summary["category_fill_count"] += 1
        elif (
            static_category
            and dynamic_category
            and not _shadow_text_equal(static_category, dynamic_category)
        ):
            summary["category_disagreement_count"] += 1

        if not _shadow_text_equal(static.normalized_brand, dynamic.normalized_brand):
            summary["brand_difference_count"] += 1
        if not _shadow_text_equal(static.normalized_model, dynamic.normalized_model):
            summary["model_difference_count"] += 1
        if not _shadow_mapping_equal(static.normalized_identity, dynamic.normalized_identity):
            summary["identity_difference_count"] += 1
        if not _shadow_mapping_equal(static.normalized_variant, dynamic.normalized_variant):
            summary["variant_difference_count"] += 1
        if not _shadow_mapping_equal(
            static.normalized_descriptive,
            dynamic.normalized_descriptive,
        ):
            summary["descriptive_difference_count"] += 1

        after = sum(summary[counter] for counter in field_counters)
        summary["field_difference_count"] += after - before
        if after > before:
            summary["changed_candidate_count"] += 1
    return summary


def _category_name(candidate: NormalizedCandidate, taxonomy: Taxonomy) -> str | None:
    if not candidate.normalized_category_id:
        return None
    category = taxonomy.get_category(candidate.normalized_category_id)
    return category.category_name if category else candidate.normalized_category_id


def _shadow_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = _WHITESPACE_RE.sub(" ", unicodedata.normalize("NFKC", value)).strip()
    return normalized.casefold() or None


def _shadow_text_equal(left: str | None, right: str | None) -> bool:
    return _shadow_text(left) == _shadow_text(right)


def _shadow_mapping_equal(left: dict[str, str], right: dict[str, str]) -> bool:
    if set(left) != set(right):
        return False
    return all(_shadow_text_equal(left[key], right[key]) for key in left)


def apply_canonicalization_patch(
    baseline: NormalizedCandidate,
    proposal: ProductCanonicalizationItem,
    taxonomy: Taxonomy,
    *,
    min_confidence: float,
) -> tuple[NormalizedCandidate, int]:
    """将单条模型补丁合并到规则基线；已有结构化字段永远优先。"""

    normalizer = TaxonomyNormalizer(taxonomy)
    offer = baseline.offer
    evidence = {item.field_path: item for item in proposal.evidence}
    failures = list(baseline.normalization_failures)
    rejected = 0

    category_id = baseline.normalized_category_id
    if proposal.category_id:
        proposed_category = taxonomy.resolve_category(proposal.category_id)[0]
        if category_id is not None:
            if proposed_category and proposed_category != category_id:
                rejected += 1
                failures.append("canonicalization_conflict:category_id")
        elif _evidence_is_valid(offer, evidence.get("category_id"), min_confidence):
            if proposed_category:
                category_id = proposed_category
            else:
                rejected += 1
                failures.append("canonicalization_rejected:category_id")
        else:
            rejected += 1
            failures.append("canonicalization_rejected:category_id")

    brand = baseline.normalized_brand
    if proposal.brand:
        proposed_brand = taxonomy.normalize_brand(proposal.brand)
        if brand is not None:
            if proposed_brand and proposed_brand != brand:
                rejected += 1
                failures.append("canonicalization_conflict:brand")
        elif _evidence_is_valid(offer, evidence.get("brand"), min_confidence):
            if proposed_brand:
                brand = proposed_brand
            else:
                rejected += 1
                failures.append("canonicalization_rejected:brand")
        else:
            rejected += 1
            failures.append("canonicalization_rejected:brand")

    model = baseline.normalized_model
    if proposal.model:
        proposed_model = taxonomy.normalize_model(proposal.model, category_id)
        if model is not None:
            if proposed_model and proposed_model != model:
                rejected += 1
                failures.append("canonicalization_conflict:model")
        elif _evidence_is_valid(offer, evidence.get("model"), min_confidence):
            if proposed_model:
                model = proposed_model
            else:
                rejected += 1
                failures.append("canonicalization_rejected:model")
        else:
            rejected += 1
            failures.append("canonicalization_rejected:model")

    identity = dict(baseline.normalized_identity)
    variant = dict(baseline.normalized_variant)
    for bucket_name, values, target, expected_role in (
        ("identity_attributes", proposal.identity_attributes, identity, "identity"),
        ("variant_attributes", proposal.variant_attributes, variant, "variant"),
    ):
        for key, raw_value in values.items():
            path = f"{bucket_name}.{key}"
            normalized_value = normalizer.normalize_attribute(category_id, key, raw_value)
            if key in target:
                if normalized_value and normalized_value != target[key]:
                    rejected += 1
                    failures.append(f"canonicalization_conflict:{path}")
                continue
            if (
                not category_id
                or taxonomy.attribute_role(category_id, key) != expected_role
                or normalized_value is None
                or not _evidence_is_valid(offer, evidence.get(path), min_confidence)
            ):
                rejected += 1
                failures.append(f"canonicalization_rejected:{path}")
                continue
            target[key] = normalized_value

    failures.extend(
        f"canonicalization_unresolved:{field_name}" for field_name in proposal.unresolved_fields
    )
    normalized_title = canonical_identity_title(category_id, brand, model, identity)
    normalized_offer = offer.model_copy(
        update={"normalized_title": normalized_title or offer.normalized_title}
    )
    return (
        baseline.model_copy(
            update={
                "offer": normalized_offer,
                "normalized_category_id": category_id,
                "normalized_brand": brand,
                "normalized_model": model,
                "normalized_identity": identity,
                "normalized_variant": variant,
                "normalization_failures": list(dict.fromkeys(failures)),
            }
        ),
        rejected,
    )


def _evidence_is_valid(
    offer: Offer,
    evidence: CanonicalFieldEvidence | None,
    min_confidence: float,
) -> bool:
    if evidence is None or evidence.confidence < min_confidence:
        return False
    needle = _normalize_evidence_text(evidence.raw_value)
    return bool(needle) and needle in _normalize_evidence_text(_offer_source_blob(offer))


def _offer_source_blob(offer: Offer) -> str:
    payload = {
        "title": offer.title,
        "category_id": offer.category_id,
        "brand": offer.brand,
        "model": offer.model,
        "identity_attributes": offer.identity_attributes,
        "variant_attributes": offer.variant_attributes,
        "descriptive_attributes": offer.descriptive_attributes,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _normalize_evidence_text(value: str) -> str:
    return _WHITESPACE_RE.sub(" ", unicodedata.normalize("NFKC", value).casefold()).strip()


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


async def dynamic_canonicalize_offers(
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
    """动态两阶段归一化：GenericNormalizer → Schema 校验 → 字段级采纳。

    每个 schema batch 独立失败回退，确保某一批模型异常不会阻断其余候选或检索。
    """

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
    induce_schema = getattr(schema_inducer, "induce_schema", None) or getattr(
        schema_inducer, "induce", None
    )
    canonicalize_dynamic = getattr(canonicalizer, "canonicalize_dynamic", None) or getattr(
        canonicalizer, "canonicalize", None
    )
    if induce_schema is None or canonicalize_dynamic is None:
        _metric(
            metrics,
            "open_world_candidate_total",
            len(offers),
            labels={"decision": "baseline"},
        )
        return ProductCanonicalizationRun(
            candidates=baseline,
            notices=["动态商品 Schema 端口方法不可用，已使用通用规则基线"],
            fallback_batches=1,
        )

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
                proposal = await induce_schema(batch_offers)
                verified = verify_dynamic_schema(
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
                schema = verified
                demoted_count = _count_role_demotions(proposal, verified)
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
            except Exception as exc:
                del exc
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
        assert schema is not None
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
                    if (
                        candidate_result.schema_id == schema.schema_id
                        and all(item.offer_id in expected_ids for item in candidate_result.items)
                    ):
                        result = candidate_result
                        total_cache_hits += 1
                        _metric(metrics, "dynamic_canonicalization_cache_hit_total")
                except Exception:
                    result = None
            if result is None:
                try:
                    result = await canonicalize_dynamic(canonical_offers, schema)
                    assert result is not None
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


def _dynamic_field_kind(field_path: str) -> str:
    if field_path == "category_concept":
        return "category"
    if field_path in {"brand", "model"}:
        return "core"
    if field_path.startswith("unresolved:"):
        return "unresolved"
    return "attribute"


def _count_role_demotions(proposal: Any, verified: VerifiedDynamicSchema) -> int:
    verified_by_concept = {
        concept.local_concept_id: concept for concept in verified.concepts
    }
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
