"""候选比较服务：复用既有归一化、同款、SKU 和排序算法。"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field as dc_field
from typing import Any, cast

from shijiajing_agent.contracts import (
    Availability,
    MatchPair,
    NormalizedCandidate,
    Preference,
    PriceBasis,
    RankedGroup,
    RetrievalCandidate,
    ShoppingConstraints,
    SkuGroup,
    SortBy,
)
from shijiajing_agent.domain.filters import HardFilterBuilder, offer_matches_hard_filters
from shijiajing_agent.domain.product_canonicalization import canonicalize_offers
from shijiajing_agent.domain.ranking import GroupRanker
from shijiajing_agent.domain.requirements import (
    build_semantic_requirements,
    qualify_candidate,
)
from shijiajing_agent.domain.same_item import default_same_item_matcher
from shijiajing_agent.domain.sku import SkuSplitter, spu_id_for
from shijiajing_agent.domain.taxonomy import Taxonomy
from shijiajing_agent.ports.cache import VersionedCachePort
from shijiajing_agent.ports.models import (
    DynamicProductCanonicalizationPort,
    DynamicSchemaInductionPort,
)
from shijiajing_agent.ports.observability import MetricsPort
from shijiajing_agent.rag_contracts import (
    CandidateAssessment,
    RequirementMatch,
    RequirementState,
)


@dataclass(frozen=True)
class ComparisonResult:
    ranked_groups: list[RankedGroup]
    normalized_candidates: list[NormalizedCandidate]
    review_pairs: list[MatchPair]
    model_calls: int = 0
    fallback_used: bool = False
    notices: list[str] | None = None
    requirement_matches: list[RequirementMatch] = dc_field(default_factory=list[RequirementMatch])
    excluded_offer_ids: list[str] = dc_field(default_factory=list[str])
    assessment: CandidateAssessment | None = None


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
        requirements = build_semantic_requirements(constraints)
        hard_filters = HardFilterBuilder().build(constraints)
        qualified: list[NormalizedCandidate] = []
        requirement_matches: list[RequirementMatch] = []
        excluded_offer_ids: list[str] = []
        for item in normalized:
            qualification = qualify_candidate(item, requirements)
            requirement_matches.extend(qualification.matches)
            if (
                qualification.eligible
                and item.offer.availability is not Availability.UNAVAILABLE
                and offer_matches_hard_filters(item.offer, hard_filters)
            ):
                qualified.append(item)
            else:
                excluded_offer_ids.append(item.offer_id)
        notices = list(canonicalization.notices or [])
        if excluded_offer_ids:
            notices.append(f"{len(excluded_offer_ids)} 条候选未通过当前硬要求资格校验")
        matcher = default_same_item_matcher(
            accept_threshold=self._accept_threshold,
            review_threshold=self._review_threshold,
        )
        pairs = matcher.generate_candidates(qualified)
        judged = [matcher.judge_pair(qualified[left], qualified[right]) for left, right in pairs]
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
        pair_confidences = {_pair_key(pair.a_id, pair.b_id): pair.score for pair in judged}
        clusters = matcher.cluster(qualified, pairs)
        if split_offer_ids:
            split_clusters: list[list[int]] = []
            for cluster in clusters:
                remaining = [
                    index for index in cluster if qualified[index].offer_id not in split_offer_ids
                ]
                split_clusters.extend([[index] for index in cluster if index not in remaining])
                if remaining:
                    split_clusters.append(remaining)
            clusters = split_clusters
        clusters = _split_price_incompatible_clusters(qualified, clusters)
        splitter = SkuSplitter(self._taxonomy)
        groups: list[SkuGroup] = []
        for cluster in clusters:
            members = [qualified[index] for index in cluster]
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
            notices=notices,
            requirement_matches=requirement_matches,
            excluded_offer_ids=excluded_offer_ids,
            assessment=_build_assessment(candidates, requirement_matches, len(groups)),
        )


def _build_assessment(
    candidates: list[RetrievalCandidate],
    matches: list[RequirementMatch],
    comparable_groups: int,
) -> CandidateAssessment:
    counts: dict[str, dict[RequirementState, int]] = {}
    for match in matches:
        per_state = counts.setdefault(match.requirement_id, {})
        per_state[match.state] = per_state.get(match.state, 0) + 1
    platforms = {candidate.offer.platform for candidate in candidates}
    unknown = sum(match.state is RequirementState.UNKNOWN for match in matches)
    return CandidateAssessment(
        total_hits=len(candidates),
        unique_offers=len({candidate.offer.offer_id for candidate in candidates}),
        selected_window=len(candidates),
        requirement_counts=counts,
        comparable_groups=comparable_groups,
        platform_count=len(platforms),
        unassessed=unknown,
        gaps=["requirement_unknown"] if unknown else [],
    )


def _split_price_incompatible_clusters(
    candidates: list[NormalizedCandidate], clusters: list[list[int]]
) -> list[list[int]]:
    """同款判断不能跨币种或混合明确不同的报价基准。"""
    result: list[list[int]] = []
    for cluster in clusters:
        by_currency: dict[str, list[int]] = {}
        for index in cluster:
            by_currency.setdefault(candidates[index].offer.currency, []).append(index)
        for currency_cluster in by_currency.values():
            known_basis = {
                candidates[index].offer.price_basis
                for index in currency_cluster
                if candidates[index].offer.price_basis is not PriceBasis.UNKNOWN
            }
            if len(known_basis) <= 1:
                if known_basis and any(
                    candidates[index].offer.price_basis is PriceBasis.UNKNOWN
                    for index in currency_cluster
                ):
                    result.extend(
                        [
                            [index]
                            for index in currency_cluster
                            if candidates[index].offer.price_basis is PriceBasis.UNKNOWN
                        ]
                    )
                    result.append(
                        [
                            index
                            for index in currency_cluster
                            if candidates[index].offer.price_basis is not PriceBasis.UNKNOWN
                        ]
                    )
                else:
                    result.append(currency_cluster)
                continue
            for basis in sorted(known_basis, key=lambda value: value.value):
                result.append(
                    [
                        index
                        for index in currency_cluster
                        if candidates[index].offer.price_basis is basis
                    ]
                )
            unknown = [
                index
                for index in currency_cluster
                if candidates[index].offer.price_basis is PriceBasis.UNKNOWN
            ]
            result.extend([[index] for index in unknown])
    return [cluster for cluster in result if cluster]


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
