"""候选比较服务：复用既有归一化、同款、SKU 和排序算法。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from shijiajing_agent.contracts import (
    MatchPair,
    NormalizedCandidate,
    Preference,
    RankedGroup,
    RetrievalCandidate,
    ShoppingConstraints,
    SkuGroup,
    SortBy,
)
from shijiajing_agent.domain.product_canonicalization import canonicalize_offers
from shijiajing_agent.domain.ranking import GroupRanker
from shijiajing_agent.domain.same_item import default_same_item_matcher
from shijiajing_agent.domain.sku import SkuSplitter, spu_id_for
from shijiajing_agent.domain.taxonomy import Taxonomy
from shijiajing_agent.ports.cache import VersionedCachePort
from shijiajing_agent.ports.models import (
    DynamicProductCanonicalizationPort,
    DynamicSchemaInductionPort,
)
from shijiajing_agent.ports.observability import MetricsPort


@dataclass(frozen=True)
class ComparisonResult:
    ranked_groups: list[RankedGroup]
    normalized_candidates: list[NormalizedCandidate]
    review_pairs: list[MatchPair]
    model_calls: int = 0
    fallback_used: bool = False
    notices: list[str] | None = None


class ComparisonService:
    def __init__(
        self,
        taxonomy: Taxonomy,
        *,
        accept_threshold: float = 0.88,
        review_threshold: float = 0.74,
        preference_weights: dict[str, dict[str, float]] | None = None,
        schema_inducer: DynamicSchemaInductionPort | None = None,
        canonicalizer: DynamicProductCanonicalizationPort | None = None,
        cache: VersionedCachePort | None = None,
        metrics: MetricsPort | None = None,
        schema_batch_size: int = 60,
        canonicalization_batch_size: int = 20,
        concept_min_confidence: float = 0.90,
        role_min_confidence: float = 0.90,
        role_min_support: int = 2,
        max_concepts: int = 16,
        max_attributes_per_concept: int = 64,
        field_min_confidence: float = 0.80,
        cache_ttl_seconds: int = 604800,
    ) -> None:
        self._taxonomy = taxonomy
        self._accept_threshold = accept_threshold
        self._review_threshold = review_threshold
        self._preference_weights = preference_weights or {}
        self._schema_inducer = schema_inducer
        self._canonicalizer = canonicalizer
        self._cache = cache
        self._metrics = metrics
        self._schema_batch_size = schema_batch_size
        self._canonicalization_batch_size = canonicalization_batch_size
        self._concept_min_confidence = concept_min_confidence
        self._role_min_confidence = role_min_confidence
        self._role_min_support = role_min_support
        self._max_concepts = max_concepts
        self._max_attributes_per_concept = max_attributes_per_concept
        self._field_min_confidence = field_min_confidence
        self._cache_ttl_seconds = cache_ttl_seconds

    async def compare_candidates(
        self,
        candidates: list[RetrievalCandidate],
        constraints: ShoppingConstraints,
        *,
        ranking_context: Any | None = None,
        split_offer_ids: set[str] | None = None,
    ) -> ComparisonResult:
        canonicalization = await canonicalize_offers(
            [item.offer for item in candidates],
            self._schema_inducer,
            self._canonicalizer,
            schema_batch_size=self._schema_batch_size,
            canonicalization_batch_size=self._canonicalization_batch_size,
            concept_min_confidence=self._concept_min_confidence,
            role_min_confidence=self._role_min_confidence,
            role_min_support=self._role_min_support,
            max_concepts=self._max_concepts,
            max_attributes_per_concept=self._max_attributes_per_concept,
            field_min_confidence=self._field_min_confidence,
            cache=self._cache,
            cache_ttl_seconds=self._cache_ttl_seconds,
            metrics=self._metrics,
        )
        normalized = canonicalization.candidates
        for item, candidate in zip(normalized, candidates, strict=True):
            item.recall_score = candidate.recall_score
        matcher = default_same_item_matcher(
            accept_threshold=self._accept_threshold,
            review_threshold=self._review_threshold,
        )
        pairs = matcher.generate_candidates(normalized)
        judged = [matcher.judge_pair(normalized[left], normalized[right]) for left, right in pairs]
        review_pairs = [
            MatchPair(
                offer_a_id=pair.a_id,
                offer_b_id=pair.b_id,
                same_item_score=pair.score,
                title_similarity=pair.title_similarity,
                identity_overlap=pair.identity_overlap,
                image_similarity=pair.image_similarity,
                source_key_signal=pair.source_key_signal,
                hard_conflicts=pair.hard_conflicts,
                verdict="review",
            )
            for pair in judged
            if pair.verdict == "review"
        ]
        pair_confidences = {
            _pair_key(pair.a_id, pair.b_id): pair.score for pair in judged
        }
        clusters = matcher.cluster(normalized, pairs)
        if split_offer_ids:
            split_clusters: list[list[int]] = []
            for cluster in clusters:
                remaining = [
                    index for index in cluster if normalized[index].offer_id not in split_offer_ids
                ]
                split_clusters.extend([[index] for index in cluster if index not in remaining])
                if remaining:
                    split_clusters.append(remaining)
            clusters = split_clusters
        splitter = SkuSplitter(self._taxonomy)
        groups: list[SkuGroup] = []
        for cluster in clusters:
            members = [normalized[index] for index in cluster]
            groups.extend(
                splitter.split_spu(members, spu_id_for(members), pair_confidences=pair_confidences)
            )
        sort_by = _constraint_sort_by(constraints.sort_by.value)
        preferences = _constraint_preferences(constraints.preferences.value)
        context = ranking_context or type("RankingContextValue", (), {})()
        ranking = GroupRanker(preference_weights=self._preference_weights).rank(
            groups,
            constraints,
            sort_by=sort_by,
            preferences=preferences,
            memory_priors=getattr(context, "memory_priors", {}),
            memory_negative_terms=getattr(context, "memory_negative_terms", []),
        )
        return ComparisonResult(
            ranked_groups=ranking.ranked,
            normalized_candidates=normalized,
            review_pairs=review_pairs,
            model_calls=canonicalization.model_calls,
            fallback_used=canonicalization.fallback_batches > 0,
            notices=canonicalization.notices,
        )


def _constraint_sort_by(raw: object) -> SortBy:
    if isinstance(raw, SortBy):
        return raw
    if isinstance(raw, str):
        try:
            return SortBy(raw)
        except ValueError:
            pass
    return SortBy.RECOMMENDED


def _constraint_preferences(raw: object) -> list[Preference]:
    values = cast(list[object], raw) if isinstance(raw, list) else []
    result: list[Preference] = []
    for value in values:
        try:
            preference = value if isinstance(value, Preference) else Preference(str(value))
        except ValueError:
            continue
        if preference not in result:
            result.append(preference)
    return result


def _pair_key(left: str, right: str) -> tuple[str, str]:
    return (left, right) if left <= right else (right, left)


__all__ = ["ComparisonResult", "ComparisonService"]
