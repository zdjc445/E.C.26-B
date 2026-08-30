"""Retrieval Agent：召回、商品归一化、同款聚类、SKU 拆分与排序。"""

from __future__ import annotations

from time import perf_counter
from typing import TypedDict

from shijiajing_agent.contracts import (
    AgentResultV2,
    AgentTaskError,
    AgentTaskUsage,
    AgentTaskV2,
    MatchPair,
    NodeStatus,
    NormalizedCandidate,
    RankedGroup,
    RetrievalCandidate,
    RetrievalQuery,
    RetrievalTaskInput,
    RetrievalTaskOutput,
    SkuGroup,
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
                self._deps.taxonomy,
                getattr(self._deps, "product_canonicalizer", None),
                enabled=self._deps.settings.product_canonicalization_enabled,
                batch_size=self._deps.settings.product_canonicalization_batch_size,
                min_confidence=self._deps.settings.product_canonicalization_min_confidence,
                cache=getattr(self._deps, "cache", None),
                cache_ttl_seconds=self._deps.settings.product_canonicalization_cache_ttl_seconds,
                metrics=self._deps.metrics,
                mode=self._deps.settings.product_canonicalization_mode,
                dynamic_schema_inducer=getattr(self._deps, "dynamic_schema_inducer", None),
                dynamic_product_canonicalizer=getattr(
                    self._deps, "dynamic_product_canonicalizer", None
                ),
                dynamic_schema_batch_size=self._deps.settings.dynamic_schema_batch_size,
                dynamic_concept_min_confidence=(
                    self._deps.settings.dynamic_schema_concept_min_confidence
                ),
                dynamic_role_min_confidence=(
                    self._deps.settings.dynamic_schema_role_min_confidence
                ),
                dynamic_role_min_support=self._deps.settings.dynamic_schema_role_min_support,
                dynamic_field_min_confidence=(
                    self._deps.settings.dynamic_canonicalization_field_min_confidence
                ),
            )
            normalized = canonicalization.candidates
            for item, candidate in zip(normalized, retrieval.candidates, strict=True):
                item.recall_score = candidate.recall_score
            matcher = default_same_item_matcher(
                self._deps.taxonomy,
                accept_threshold=(
                    self._deps.settings.dynamic_same_item_accept_threshold
                    if self._deps.settings.product_canonicalization_mode in {"dynamic", "hybrid"}
                    else self._deps.settings.same_item_accept_threshold
                ),
                review_threshold=(
                    self._deps.settings.dynamic_same_item_review_threshold
                    if self._deps.settings.product_canonicalization_mode in {"dynamic", "hybrid"}
                    else self._deps.settings.same_item_review_threshold
                ),
                mode=(
                    "taxonomy"
                    if self._deps.settings.product_canonicalization_mode == "dynamic_shadow"
                    else self._deps.settings.product_canonicalization_mode
                ),
            )
            pairs = matcher.generate_candidates(normalized)
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
                for left, right in pairs
                if (pair := matcher.judge_pair(normalized[left], normalized[right])).verdict
                == "review"
            ]
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
            splitter = SkuSplitter(
                self._deps.taxonomy,
                dynamic=self._deps.settings.product_canonicalization_mode in {"dynamic", "hybrid"},
            )
            groups: list[SkuGroup] = []
            for cluster in clusters:
                members = [normalized[index] for index in cluster]
                groups.extend(splitter.split_spu(members, spu_id_for(members)))
            ranking = GroupRanker(preference_weights=self._deps.settings.preference_weights).rank(
                groups,
                data.constraints,
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


__all__ = ["RetrievalAgent", "RetrievalAgentState"]
