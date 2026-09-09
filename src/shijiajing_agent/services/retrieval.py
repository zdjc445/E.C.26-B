"""一次检索工具与检索-比较组合工具。"""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass

from shijiajing_agent.agent_runtime.contracts import AgentRuntimeUsage
from shijiajing_agent.contracts import (
    HardFilters,
    ImageRef,
    RecognitionResult,
    RetrievalCandidate,
    RetrievalQuery,
    ShoppingConstraints,
)
from shijiajing_agent.domain.candidate_selection import select_candidate_window
from shijiajing_agent.domain.filters import HardFilterBuilder
from shijiajing_agent.domain.retrieval_fusion import BestQueryChannelRRF
from shijiajing_agent.ports.models import QueryRewritePort
from shijiajing_agent.ports.retrieval import ProductRetrievalPort, RetrievalResult
from shijiajing_agent.rag_contracts import (
    ChannelStatus,
    PreparedQuery,
    QueryPlan,
    QuerySource,
)
from shijiajing_agent.services.comparison import ComparisonResult, ComparisonService


@dataclass(frozen=True)
class SearchOnceResult:
    query: RetrievalQuery
    candidates: list[RetrievalCandidate]
    retrieval: RetrievalResult
    usage: AgentRuntimeUsage
    plan: QueryPlan | None = None
    query_results: tuple[RetrievalResult, ...] = ()


@dataclass(frozen=True)
class SearchAndCompareResult:
    search: SearchOnceResult
    comparison: ComparisonResult
    usage: AgentRuntimeUsage


class RetrievalService:
    def __init__(
        self,
        query_rewrite: QueryRewritePort,
        retrieval: ProductRetrievalPort,
        comparison: ComparisonService,
        *,
        category_names: dict[str, str] | None = None,
        top_k: int = 100,
        union_limit: int = 200,
        candidate_window_limit: int = 60,
        rrf_k: int = 60,
        initial_max_queries: int = 3,
        query_concurrency: int = 2,
    ) -> None:
        self._query_rewrite = query_rewrite
        self._retrieval = retrieval
        self._comparison = comparison
        self._category_names = category_names or {}
        self._top_k = top_k
        self._union_limit = union_limit
        self._candidate_window_limit = candidate_window_limit
        self._fusion = BestQueryChannelRRF(rrf_k)
        self._initial_max_queries = max(1, initial_max_queries)
        self._query_concurrency = max(1, min(4, query_concurrency))

    @property
    def comparison(self) -> ComparisonService:
        return self._comparison

    async def prepare_queries(
        self,
        query_text: str,
        constraints: ShoppingConstraints,
        *,
        recognition: RecognitionResult | None = None,
        soft_terms: list[str] | None = None,
        max_queries: int | None = None,
        source: QuerySource = QuerySource.ORIGINAL,
        constraints_version: int = 1,
    ) -> tuple[QueryPlan, AgentRuntimeUsage]:
        """准备有界查询计划；模型只能提供文本建议，硬过滤由本地重建。"""
        hard_filters = HardFilterBuilder().build(constraints)
        model_calls = 0
        rewritten: RetrievalQuery | QueryPlan | None = None
        try:
            rewritten = await self._query_rewrite.rewrite(query_text, constraints, recognition)
            model_calls = 1
        except Exception:
            rewritten = None

        limit = max(1, max_queries or self._initial_max_queries)
        if isinstance(rewritten, QueryPlan):
            proposed = [rewritten.original_query, *rewritten.variants]
            primary = proposed[0] if proposed else None
            variant_texts = [item for item in proposed[1:] if item.text != query_text]
            primary_soft = primary.soft_terms if primary is not None else []
            primary_negative = primary.negative_terms if primary is not None else []
        else:
            primary = rewritten
            variant_texts = []
            primary_soft = primary.soft_terms if primary is not None else []
            primary_negative = primary.negative_terms if primary is not None else []

        combined_soft = _unique_strings([*(soft_terms or []), *primary_soft])
        prepared: list[PreparedQuery] = [
            self._prepared_query(
                query_text,
                hard_filters=hard_filters,
                soft_terms=combined_soft,
                negative_terms=primary_negative,
                constraints_version=constraints_version,
                source=source,
            )
        ]
        for item in variant_texts:
            text = item.text.strip()
            if not text or text == prepared[0].text:
                continue
            prepared.append(
                self._prepared_query(
                    text,
                    hard_filters=hard_filters,
                    soft_terms=_unique_strings([*combined_soft, *item.soft_terms]),
                    negative_terms=item.negative_terms,
                    constraints_version=constraints_version,
                    source=(
                        QuerySource.SUPPLEMENT
                        if source is QuerySource.SUPPLEMENT
                        else QuerySource.INITIAL_EXPANSION
                    ),
                )
            )
            if len(prepared) >= limit:
                break
        usage = AgentRuntimeUsage(model_calls=model_calls)
        return (
            QueryPlan(
                original_query=prepared[0],
                variants=prepared[1:],
                usage=usage,
            ),
            usage,
        )

    async def execute_prepared_query(
        self,
        prepared: PreparedQuery,
        *,
        image: ImageRef | None = None,
        top_k: int | None = None,
        union_limit: int | None = None,
    ) -> SearchOnceResult:
        query = RetrievalQuery(
            query_text=prepared.text,
            hard_filters=prepared.hard_filters,
            soft_terms=prepared.soft_terms,
            negative_terms=prepared.negative_terms,
        )
        result = await self._retrieval.search(
            query,
            image=image,
            top_k=top_k or self._top_k,
            union_limit=union_limit or self._union_limit,
            category_names=self._category_names,
        )
        candidates = [
            item.model_copy(
                update={"query_ids": list(dict.fromkeys([*item.query_ids, prepared.query_id]))}
            )
            for item in result.candidates
        ]
        result = RetrievalResult(
            candidates=candidates,
            total_found=result.total_found,
            fallback_used=result.fallback_used,
            fallback_reason=result.fallback_reason,
            channel_counts=result.channel_counts,
            index_version=result.index_version,
            fusion_version=result.fusion_version,
            rerank_version=result.rerank_version,
            channel_results=[
                channel.model_copy(
                    update={
                        "query_id": prepared.query_id,
                        "hits": [
                            hit.model_copy(
                                update={
                                    "query_ids": list(
                                        dict.fromkeys([*hit.query_ids, prepared.query_id])
                                    )
                                }
                            )
                            for hit in channel.hits
                        ],
                    }
                )
                for channel in result.channel_results
            ],
            channel_health=result.channel_health,
            selected_candidates=candidates,
            truncated_count=result.truncated_count,
        )
        return SearchOnceResult(
            query=query,
            candidates=candidates,
            retrieval=result,
            usage=AgentRuntimeUsage(retrieval_calls=1),
            plan=None,
            query_results=(result,),
        )

    async def execute_prepared_query_batch(
        self,
        prepared: list[PreparedQuery],
        *,
        image: ImageRef | None = None,
        top_k: int | None = None,
        union_limit: int | None = None,
    ) -> list[SearchOnceResult]:
        """用有界并发执行已批准查询；查询文本不再触发二次 rewrite。"""
        semaphore = asyncio.Semaphore(self._query_concurrency)

        async def run(item: PreparedQuery) -> SearchOnceResult:
            async with semaphore:
                return await self.execute_prepared_query(
                    item, image=image, top_k=top_k, union_limit=union_limit
                )

        return list(await asyncio.gather(*(run(item) for item in prepared)))

    async def search_once(
        self,
        query_text: str,
        constraints: ShoppingConstraints,
        *,
        recognition: RecognitionResult | None = None,
        image: ImageRef | None = None,
        soft_terms: list[str] | None = None,
        top_k: int | None = None,
        union_limit: int | None = None,
        constraints_version: int = 1,
    ) -> SearchOnceResult:
        plan, plan_usage = await self.prepare_queries(
            query_text,
            constraints,
            recognition=recognition,
            soft_terms=soft_terms,
            constraints_version=constraints_version,
        )
        prepared = [plan.original_query, *plan.variants]
        results = await self.execute_prepared_query_batch(
            prepared, image=image, top_k=top_k, union_limit=union_limit
        )
        result = self._merge_retrieval_results(
            prepared, results, union_limit=union_limit or self._union_limit
        )
        window = select_candidate_window(result.candidates, limit=self._candidate_window_limit)
        result = RetrievalResult(
            candidates=result.candidates,
            total_found=result.total_found,
            fallback_used=result.fallback_used,
            fallback_reason=result.fallback_reason,
            channel_counts=result.channel_counts,
            index_version=result.index_version,
            fusion_version=result.fusion_version,
            rerank_version=result.rerank_version,
            channel_results=result.channel_results,
            channel_health=result.channel_health,
            selected_candidates=window.candidates,
            truncated_count=window.truncated_count,
        )
        query = RetrievalQuery(
            query_text=plan.original_query.text,
            hard_filters=plan.original_query.hard_filters,
            soft_terms=plan.original_query.soft_terms,
            negative_terms=plan.original_query.negative_terms,
        )
        return SearchOnceResult(
            query=query,
            candidates=window.candidates,
            retrieval=result,
            usage=plan_usage.add(
                AgentRuntimeUsage(
                    retrieval_calls=sum(item.usage.retrieval_calls for item in results)
                )
            ),
            plan=plan,
            query_results=tuple(item.retrieval for item in results),
        )

    @staticmethod
    def _prepared_query(
        text: str,
        *,
        hard_filters: HardFilters,
        soft_terms: list[str],
        negative_terms: list[str],
        constraints_version: int,
        source: QuerySource,
    ) -> PreparedQuery:
        fingerprint_payload = {
            "text": text,
            "hard_filters": hard_filters.model_dump(mode="json"),
            "soft_terms": soft_terms,
            "negative_terms": negative_terms,
            "constraints_version": constraints_version,
            "source": source.value,
        }
        fingerprint = hashlib.sha256(
            json.dumps(
                fingerprint_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
        ).hexdigest()
        query_id = f"q:{fingerprint[:24]}"
        return PreparedQuery(
            query_id=query_id,
            text=text,
            hard_filters=hard_filters,
            soft_terms=soft_terms,
            negative_terms=negative_terms,
            constraints_version=constraints_version,
            source=source,
            fingerprint=fingerprint,
        )

    def _merge_retrieval_results(
        self,
        prepared: list[PreparedQuery],
        results: list[SearchOnceResult],
        *,
        union_limit: int,
    ) -> RetrievalResult:
        query_channels: dict[str, dict[str, list[RetrievalCandidate]]] = {}
        usable_channels: set[str] = set()
        health_by_channel: dict[str, list[ChannelStatus]] = {}
        fallback_used = False
        fallback_reason: str | None = None
        index_version: str | None = None
        for query, item in zip(prepared, results, strict=True):
            per_channel: dict[str, list[RetrievalCandidate]] = {}
            if item.retrieval.channel_results:
                for channel_result in item.retrieval.channel_results:
                    channel = channel_result.channel.value
                    health_by_channel.setdefault(channel, []).append(channel_result.status)
                    if channel_result.status in {ChannelStatus.SUCCESS, ChannelStatus.EMPTY}:
                        usable_channels.add(channel)
                    values = list(channel_result.hits)
                    if values:
                        per_channel[channel] = values
            else:
                fields = {
                    "dense": "dense_text_score",
                    "sparse": "sparse_score",
                    "image": "image_similarity",
                }
                for channel, field in fields.items():
                    values = [
                        candidate.model_copy(
                            update={"recall_score": float(getattr(candidate, field) or 0.0)}
                        )
                        for candidate in item.candidates
                        if getattr(candidate, field) is not None
                    ]
                    if values:
                        per_channel[channel] = sorted(
                            values,
                            key=lambda candidate: (
                                -candidate.recall_score,
                                candidate.offer.offer_id,
                            ),
                        )
                        usable_channels.add(channel)
                    if channel in item.retrieval.channel_counts:
                        usable_channels.add(channel)
                        health_by_channel.setdefault(channel, []).append(ChannelStatus.SUCCESS)
            query_channels[query.query_id] = per_channel
            fallback_used = fallback_used or item.retrieval.fallback_used
            fallback_reason = fallback_reason or item.retrieval.fallback_reason
            index_version = index_version or item.retrieval.index_version
        fused = self._fusion.fuse(
            query_channels,
            union_limit,
            usable_channels=sorted(usable_channels),
        )
        channel_counts: dict[str, int] = {}
        for item in results:
            for channel, count in item.retrieval.channel_counts.items():
                channel_counts[channel] = channel_counts.get(channel, 0) + count
        return RetrievalResult(
            candidates=fused,
            total_found=len(fused),
            fallback_used=fallback_used,
            fallback_reason=fallback_reason,
            channel_counts=channel_counts,
            index_version=index_version,
            fusion_version=self._fusion.version,
            channel_results=[
                channel for item in results for channel in item.retrieval.channel_results
            ],
            channel_health={
                channel: _aggregate_channel_status(statuses)
                for channel, statuses in health_by_channel.items()
            },
            selected_candidates=fused,
        )

    async def search_and_compare(
        self,
        query_text: str,
        constraints: ShoppingConstraints,
        *,
        recognition: RecognitionResult | None = None,
        image: ImageRef | None = None,
        soft_terms: list[str] | None = None,
        ranking_context: object | None = None,
        split_offer_ids: set[str] | None = None,
        constraints_version: int = 1,
    ) -> SearchAndCompareResult:
        search = await self.search_once(
            query_text,
            constraints,
            recognition=recognition,
            image=image,
            soft_terms=soft_terms,
            constraints_version=constraints_version,
        )
        comparison = await self._comparison.compare_candidates(
            search.candidates,
            constraints,
            ranking_context=ranking_context,
            split_offer_ids=split_offer_ids,
        )
        usage = search.usage.add(
            AgentRuntimeUsage(
                tool_calls=1,
                model_calls=comparison.model_calls,
            )
        )
        return SearchAndCompareResult(search=search, comparison=comparison, usage=usage)


def _aggregate_channel_status(statuses: list[ChannelStatus]) -> ChannelStatus:
    """保留跨查询健康诊断，同时不影响有成功命中的通道参与融合。"""
    for status in (ChannelStatus.FAILED, ChannelStatus.UNAVAILABLE):
        if status in statuses:
            return status
    if ChannelStatus.SUCCESS in statuses:
        return ChannelStatus.SUCCESS
    return ChannelStatus.EMPTY


def _unique_strings(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


__all__ = ["RetrievalService", "SearchAndCompareResult", "SearchOnceResult"]
