"""Retrieval Agent：召回、商品归一化、同款聚类、SKU 拆分与排序。"""

from __future__ import annotations

from time import perf_counter
from typing import TypedDict, cast

from shijiajing_agent.contracts import (
    AgentResultV2,
    AgentTaskError,
    AgentTaskUsage,
    AgentTaskV2,
    MatchPair,
    NodeStatus,
    NormalizedCandidate,
    Preference,
    RankedGroup,
    RetrievalCandidate,
    RetrievalQuery,
    RetrievalTaskInput,
    RetrievalTaskOutput,
    SkuGroup,
    SortBy,
    SpecialistAgentName,
)
from shijiajing_agent.domain.filters import HardFilterBuilder
from shijiajing_agent.domain.product_canonicalization import canonicalize_offers
from shijiajing_agent.domain.ranking import GroupRanker
from shijiajing_agent.domain.same_item import default_same_item_matcher
from shijiajing_agent.domain.sku import SkuSplitter, spu_id_for
from shijiajing_agent.multi_agent.agents.base import fixed_error, result_for, task_usage
from shijiajing_agent.ports.dependencies import AgentDependenciesPort


class RetrievalAgentState(TypedDict, total=False):
    task_id: str
    query: RetrievalQuery | None
    candidates: list[RetrievalCandidate]
    normalized_candidates: list[NormalizedCandidate]
    spu_clusters: list[list[int]]
    sku_groups: list[SkuGroup]
    ranked_groups: list[RankedGroup]
    error: AgentTaskError | None
    usage: AgentTaskUsage


class RetrievalAgent:
    name = SpecialistAgentName.RETRIEVAL

    def __init__(self, deps: AgentDependenciesPort) -> None:
        self._deps = deps

    async def execute(self, task: AgentTaskV2) -> AgentResultV2:
        start = perf_counter()
        data = task.input
        if not isinstance(data, RetrievalTaskInput):
            return result_for(
                task,
                status=NodeStatus.FAILED,
                error=fixed_error("INVALID_TASK_INPUT", "Retrieval input 类型不匹配"),
            )
        try:
            hard_filters = HardFilterBuilder().build(data.constraints)
            try:
                query = await self._deps.query_rewrite.rewrite(
                    data.query_text, data.constraints, data.recognition
                )
                if query.hard_filters != hard_filters:
                    query = query.model_copy(update={"hard_filters": hard_filters})
            except Exception:
                query = RetrievalQuery(query_text=data.query_text, hard_filters=hard_filters)
            retrieval = await self._deps.retrieval.search(
                query,
                image=None,
                top_k=data.top_k,
                union_limit=data.union_limit,
                category_names={
                    category.category_id: category.category_name
                    for category in self._deps.taxonomy.categories()
                },
            )
            canonicalization = await canonicalize_offers(
                [item.offer for item in retrieval.candidates],
                getattr(self._deps, "dynamic_schema_inducer", None),
                getattr(self._deps, "dynamic_product_canonicalizer", None),
                schema_batch_size=self._deps.settings.dynamic_schema_batch_size,
                canonicalization_batch_size=(
                    self._deps.settings.dynamic_canonicalization_batch_size
                ),
                concept_min_confidence=(self._deps.settings.dynamic_schema_concept_min_confidence),
                role_min_confidence=(self._deps.settings.dynamic_schema_role_min_confidence),
                role_min_support=self._deps.settings.dynamic_schema_role_min_support,
                max_concepts=self._deps.settings.dynamic_schema_max_concepts,
                max_attributes_per_concept=(
                    self._deps.settings.dynamic_schema_max_attributes_per_concept
                ),
                field_min_confidence=(
                    self._deps.settings.dynamic_canonicalization_field_min_confidence
                ),
                cache=getattr(self._deps, "cache", None),
                cache_ttl_seconds=self._deps.settings.dynamic_schema_cache_ttl_seconds,
                metrics=self._deps.metrics,
            )
            normalized = canonicalization.candidates
            for item, candidate in zip(normalized, retrieval.candidates, strict=True):
                item.recall_score = candidate.recall_score
            matcher = default_same_item_matcher(
                accept_threshold=self._deps.settings.same_item_accept_threshold,
                review_threshold=self._deps.settings.same_item_review_threshold,
            )
            pairs = matcher.generate_candidates(normalized)
            judged_pairs = [
                matcher.judge_pair(normalized[left], normalized[right]) for left, right in pairs
            ]
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
                for pair in judged_pairs
                if pair.verdict == "review"
            ]
            pair_confidences: dict[tuple[str, str], float] = {
                _pair_key(pair.a_id, pair.b_id): pair.score for pair in judged_pairs
            }
            clusters = matcher.cluster(normalized, pairs)
            if data.same_item_review_action == "split" and data.same_item_review_offer_ids:
                review_ids = set(data.same_item_review_offer_ids)
                split_clusters: list[list[int]] = []
                for cluster in clusters:
                    remaining = [
                        index for index in cluster if normalized[index].offer_id not in review_ids
                    ]
                    split_clusters.extend([[index] for index in cluster if index not in remaining])
                    if remaining:
                        split_clusters.append(remaining)
                clusters = split_clusters
            splitter = SkuSplitter(self._deps.taxonomy)
            groups: list[SkuGroup] = []
            for cluster in clusters:
                members = [normalized[index] for index in cluster]
                groups.extend(
                    splitter.split_spu(
                        members,
                        spu_id_for(members),
                        pair_confidences=pair_confidences,
                    )
                )
            sort_by = _constraint_sort_by(data.constraints.sort_by.value)
            preferences = _constraint_preferences(data.constraints.preferences.value)
            ranking = GroupRanker(preference_weights=self._deps.settings.preference_weights).rank(
                groups,
                data.constraints,
                sort_by=sort_by,
                preferences=preferences,
                memory_priors=data.ranking_context.memory_priors,
                memory_negative_terms=data.ranking_context.memory_negative_terms,
            )
            output = RetrievalTaskOutput(
                query=query,
                candidates=retrieval.candidates,
                normalized_candidates=normalized,
                ranked_groups=ranking.ranked,
                fallback_used=retrieval.fallback_used,
                same_item_review_pairs=review_pairs,
            )
            return result_for(
                task,
                status=NodeStatus.FALLBACK if retrieval.fallback_used else NodeStatus.SUCCESS,
                output=output,
                usage=task_usage(
                    start,
                    calls=canonicalization.model_calls,
                    fallback=canonicalization.fallback_batches > 0,
                ),
            )
        except Exception:
            return result_for(
                task,
                status=NodeStatus.FAILED,
                error=fixed_error(
                    "RETRIEVAL_UNAVAILABLE", "检索不可用，未放宽用户硬过滤", retryable=True
                ),
                usage=task_usage(start),
            )


def _constraint_sort_by(raw: object) -> SortBy:
    """把约束中的宽类型值收敛成排序枚举；非法值安全回退综合推荐。"""

    if isinstance(raw, SortBy):
        return raw
    if isinstance(raw, str):
        try:
            return SortBy(raw)
        except ValueError:
            pass
    return SortBy.RECOMMENDED


def _constraint_preferences(raw: object) -> list[Preference]:
    """把用户显式偏好收敛成去重后的 Preference 列表。"""

    values = cast(list[object], raw) if isinstance(raw, list) else []
    preferences: list[Preference] = []
    for value in values:
        try:
            preference = value if isinstance(value, Preference) else Preference(str(value))
        except ValueError:
            continue
        if preference not in preferences:
            preferences.append(preference)
    return preferences


def _pair_key(left: str, right: str) -> tuple[str, str]:
    return (left, right) if left <= right else (right, left)


__all__ = ["RetrievalAgent", "RetrievalAgentState"]
