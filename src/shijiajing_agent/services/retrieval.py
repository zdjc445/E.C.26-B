"""一次检索工具与检索-比较组合工具。"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import re
import time
from collections.abc import Iterable
from dataclasses import dataclass
from typing import cast

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
from shijiajing_agent.domain.reranker_summary import build_rerank_document, candidate_version
from shijiajing_agent.domain.retrieval_fusion import BestQueryChannelRRF
from shijiajing_agent.ports.models import QueryRewritePort
from shijiajing_agent.ports.retrieval import (
    ProductRetrievalPort,
    RerankerPort,
    RerankerStatus,
    RerankResult,
    RetrievalResult,
    begin_retrieval_usage,
    finish_retrieval_usage,
)
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
        index_manifest_id: str | None = None,
        reranker: RerankerPort | None = None,
        reranker_cache_ttl_seconds: int = 300,
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
        self._index_manifest_id = index_manifest_id or getattr(retrieval, "index_version", None)
        self._reranker = reranker
        self._reranker_cache_ttl_seconds = max(1, reranker_cache_ttl_seconds)
        self._reranker_cache: dict[str, tuple[float, RerankResult]] = {}

    @property
    def comparison(self) -> ComparisonService:
        return self._comparison

    async def prepare_queries(
        self,
        query_text: str,
        constraints: ShoppingConstraints,
        *,
        recognition: RecognitionResult | None = None,
        image_sha256: str | None = None,
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
                image_sha256=image_sha256,
                index_manifest_id=self._index_manifest_id,
            )
        ]
        seen_texts = {prepared[0].text}
        for item in variant_texts:
            text = _normalize_query_text(item.text)
            if not text or text in seen_texts:
                continue
            seen_texts.add(text)
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
                    image_sha256=image_sha256,
                    index_manifest_id=self._index_manifest_id,
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

    def prepare_explicit_queries(
        self,
        query_texts: list[str],
        constraints: ShoppingConstraints,
        *,
        constraints_version: int,
        source: QuerySource = QuerySource.SUPPLEMENT,
        assumptions_by_query: list[list[str]] | None = None,
        evidence_refs_by_query: list[list[str]] | None = None,
        image_sha256: str | None = None,
        index_manifest_id: str | None = None,
    ) -> list[PreparedQuery]:
        """把主 Agent 已批准的补查文本转成查询身份，不再触发二次改写。"""
        hard_filters = HardFilterBuilder().build(constraints)
        prepared: list[PreparedQuery] = []
        seen: set[str] = set()
        for index, raw_text in enumerate(query_texts):
            text = _normalize_query_text(raw_text)
            if not text or text in seen:
                continue
            seen.add(text)
            prepared.append(
                self._prepared_query(
                    text,
                    hard_filters=hard_filters,
                    soft_terms=[],
                    negative_terms=[],
                    constraints_version=constraints_version,
                    source=source,
                    assumptions=(assumptions_by_query or [])[index]
                    if assumptions_by_query is not None and index < len(assumptions_by_query)
                    else [],
                    evidence_refs=(evidence_refs_by_query or [])[index]
                    if evidence_refs_by_query is not None and index < len(evidence_refs_by_query)
                    else [],
                    image_sha256=image_sha256,
                    index_manifest_id=index_manifest_id or self._index_manifest_id,
                )
            )
        return prepared

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
        usage_token = begin_retrieval_usage()
        try:
            result = await self._retrieval.search(
                query,
                image=image,
                top_k=top_k or self._top_k,
                union_limit=union_limit or self._union_limit,
                category_names=self._category_names,
            )
        finally:
            measured_usage = finish_retrieval_usage(usage_token)
        if (
            prepared.index_manifest_id is not None
            and result.index_version is not None
            and prepared.index_manifest_id != result.index_version
        ):
            raise ValueError("检索结果 index manifest 与 PreparedQuery 不一致")
        result.usage = result.usage.add(measured_usage)
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
            rerank_result=result.rerank_result,
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
            usage=result.usage,
        )
        return SearchOnceResult(
            query=query,
            candidates=candidates,
            retrieval=result,
            usage=AgentRuntimeUsage(retrieval_calls=1).add(result.usage),
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

        async def run(index: int, item: PreparedQuery) -> SearchOnceResult:
            async with semaphore:
                return await self.execute_prepared_query(
                    item,
                    image=image if index == 0 else None,
                    top_k=top_k,
                    union_limit=union_limit,
                )

        return list(
            await asyncio.gather(*(run(index, item) for index, item in enumerate(prepared)))
        )

    def merge_prepared_query_results(
        self,
        prepared: list[PreparedQuery],
        results: list[SearchOnceResult],
        *,
        union_limit: int | None = None,
    ) -> RetrievalResult:
        """融合一批已执行查询；调用方可把结果与既有召回池再合并。"""
        if len(prepared) != len(results):
            raise ValueError("prepared query 与检索结果数量不一致")
        return self._merge_retrieval_results(
            prepared,
            results,
            union_limit=union_limit or self._union_limit,
        )

    @staticmethod
    def merge_candidate_pools(
        existing: list[RetrievalCandidate],
        incoming: list[RetrievalCandidate],
        *,
        union_limit: int = 200,
    ) -> list[RetrievalCandidate]:
        """按 Offer 身份合并阶段召回池，保留同一 Offer 的最佳已观测分数。"""
        merged: dict[str, RetrievalCandidate] = {}
        for candidate in [*existing, *incoming]:
            offer_id = candidate.offer.offer_id
            previous = merged.get(offer_id)
            if previous is None:
                merged[offer_id] = candidate
                continue
            merged[offer_id] = previous.model_copy(
                update={
                    "dense_text_score": _max_optional(
                        previous.dense_text_score, candidate.dense_text_score
                    ),
                    "sparse_score": _max_optional(previous.sparse_score, candidate.sparse_score),
                    "image_similarity": _max_optional(
                        previous.image_similarity, candidate.image_similarity
                    ),
                    "metadata_match": max(previous.metadata_match, candidate.metadata_match),
                    "recall_score": max(previous.recall_score, candidate.recall_score),
                    "rerank_score": _max_optional(previous.rerank_score, candidate.rerank_score),
                    "channel_sources": list(
                        dict.fromkeys([*previous.channel_sources, *candidate.channel_sources])
                    ),
                    "query_ids": list(dict.fromkeys([*previous.query_ids, *candidate.query_ids])),
                }
            )
        ordered = sorted(
            merged.values(), key=lambda item: (-item.recall_score, item.offer.offer_id)
        )
        return ordered[: max(1, union_limit)]

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
        max_queries: int | None = None,
        rerank: bool = True,
    ) -> SearchOnceResult:
        plan, plan_usage = await self.prepare_queries(
            query_text,
            constraints,
            recognition=recognition,
            image_sha256=image.sha256 if image is not None else None,
            soft_terms=soft_terms,
            max_queries=max_queries,
            constraints_version=constraints_version,
        )
        prepared = [plan.original_query, *plan.variants]
        results = await self.execute_prepared_query_batch(
            prepared, image=image, top_k=top_k, union_limit=union_limit
        )
        result = self._merge_retrieval_results(
            prepared, results, union_limit=union_limit or self._union_limit
        )
        rerank_usage = AgentRuntimeUsage()
        if rerank:
            reranked, rerank_result = await self.rerank_candidates(
                query_text,
                constraints,
                result.candidates,
                constraints_version=constraints_version,
            )
            result.candidates = reranked
            result.rerank_result = rerank_result
            result.rerank_version = (
                rerank_result.model_version
                if rerank_result is not None and rerank_result.status is RerankerStatus.SUCCESS
                else None
            )
            rerank_usage = rerank_result.usage if rerank_result is not None else AgentRuntimeUsage()
        use_rerank = (
            result.rerank_result is not None
            and result.rerank_result.status is RerankerStatus.SUCCESS
        )
        window = select_candidate_window(
            result.candidates,
            limit=self._candidate_window_limit,
            use_rerank=use_rerank,
        )
        result = RetrievalResult(
            candidates=result.candidates,
            total_found=result.total_found,
            fallback_used=result.fallback_used,
            fallback_reason=result.fallback_reason,
            channel_counts=result.channel_counts,
            index_version=result.index_version,
            fusion_version=result.fusion_version,
            rerank_version=result.rerank_version,
            rerank_result=result.rerank_result,
            channel_results=result.channel_results,
            channel_health=result.channel_health,
            selected_candidates=window.candidates,
            truncated_count=window.truncated_count,
            usage=result.usage,
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
            usage=plan_usage.add(_sum_usage(item.usage for item in results)).add(rerank_usage),
            plan=plan,
            query_results=tuple(item.retrieval for item in results),
        )

    async def rerank_candidates(
        self,
        query_text: str,
        constraints: ShoppingConstraints,
        candidates: list[RetrievalCandidate],
        *,
        constraints_version: int = 1,
        deadline: float | None = None,
    ) -> tuple[list[RetrievalCandidate], RerankResult | None]:
        """对完整当前候选池精排；失败时原样返回 RRF 顺序。"""
        if self._reranker is None or not candidates:
            return candidates, None
        pool = list(candidates[: self._union_limit])
        version = candidate_version([item.offer for item in pool])
        try:
            documents = [
                build_rerank_document(
                    item.offer,
                    max_tokens=getattr(self._reranker, "document_max_tokens", 384),
                ).document
                for item in pool
            ]
        except ValueError:
            return pool, RerankResult(
                status=RerankerStatus.FAILED,
                candidate_version=version,
                fallback_reason="unsafe_or_empty_summary",
            )
        query = _build_rerank_query(query_text, constraints)
        cache_key = _rerank_cache_key(
            getattr(self._reranker, "cache_identity", "unknown"),
            query,
            version,
            constraints_version,
        )
        cached = self._reranker_cache.get(cache_key)
        if cached is not None and cached[0] > time.monotonic():
            cached_result = cached[1].model_copy(
                update={
                    "cache_hit": True,
                    "usage": AgentRuntimeUsage(reranker_cache_hits=1),
                }
            )
            return _apply_rerank(pool, cached_result), cached_result
        try:
            result = await self._reranker.rerank(
                query,
                documents,
                top_k=len(pool),
                deadline=deadline,
                candidate_version=version,
            )
        except Exception:
            result = RerankResult(
                status=RerankerStatus.FAILED,
                candidate_version=version,
                fallback_reason="adapter_exception",
            )
        if result.status is not RerankerStatus.SUCCESS:
            return pool, result
        try:
            reranked = _apply_rerank(pool, result)
        except ValueError:
            failed = result.model_copy(
                update={
                    "status": RerankerStatus.FAILED,
                    "results": [],
                    "fallback_reason": "service_result_validation_failed",
                    "usage": result.usage.model_copy(
                        update={"reranker_fallbacks": result.usage.reranker_fallbacks + 1}
                    ),
                }
            )
            return pool, failed
        self._reranker_cache[cache_key] = (
            time.monotonic() + self._reranker_cache_ttl_seconds,
            result,
        )
        return reranked, result

    @staticmethod
    def _prepared_query(
        text: str,
        *,
        hard_filters: HardFilters,
        soft_terms: list[str],
        negative_terms: list[str],
        constraints_version: int,
        source: QuerySource,
        assumptions: list[str] | None = None,
        evidence_refs: list[str] | None = None,
        image_sha256: str | None = None,
        index_manifest_id: str | None = None,
    ) -> PreparedQuery:
        fingerprint_payload = {
            "text": _normalize_query_text(text),
            "hard_filters": hard_filters.model_dump(mode="json"),
            "soft_terms": soft_terms,
            "negative_terms": negative_terms,
            "constraints_version": constraints_version,
            "image_sha256": image_sha256,
            "index_manifest_id": index_manifest_id,
            "retrieval_version": "best-query-channel-rrf-v1",
        }
        fingerprint = hashlib.sha256(
            json.dumps(
                fingerprint_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
        ).hexdigest()
        query_id = f"q:{fingerprint[:24]}"
        return PreparedQuery(
            query_id=query_id,
            text=_normalize_query_text(text),
            hard_filters=hard_filters,
            soft_terms=soft_terms,
            negative_terms=negative_terms,
            constraints_version=constraints_version,
            source=source,
            assumptions=list(assumptions or []),
            evidence_refs=list(evidence_refs or []),
            index_manifest_id=index_manifest_id,
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
        usage = AgentRuntimeUsage()
        for query, item in zip(prepared, results, strict=True):
            usage = usage.add(item.retrieval.usage)
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
            usage=usage,
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
        max_queries: int | None = None,
    ) -> SearchAndCompareResult:
        search = await self.search_once(
            query_text,
            constraints,
            recognition=recognition,
            image=image,
            soft_terms=soft_terms,
            constraints_version=constraints_version,
            max_queries=max_queries,
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


def _normalize_query_text(value: str) -> str:
    """只折叠空白，不删除型号标点或否定语义。"""
    return " ".join(value.strip().split())


def _max_optional(left: float | None, right: float | None) -> float | None:
    if left is None:
        return right
    if right is None:
        return left
    return max(left, right)


def _sum_usage(usages: Iterable[AgentRuntimeUsage]) -> AgentRuntimeUsage:
    total = AgentRuntimeUsage()
    for usage in usages:
        total = total.add(usage)
    return total


def _apply_rerank(
    candidates: list[RetrievalCandidate], result: RerankResult
) -> list[RetrievalCandidate]:
    if result.candidate_version != candidate_version([item.offer for item in candidates]):
        raise ValueError("reranker candidate version drift")
    expected = {item.offer.offer_id for item in candidates}
    actual = [item.offer_id for item in result.results]
    if set(actual) != expected or len(actual) != len(expected) or len(set(actual)) != len(actual):
        raise ValueError("reranker result ids are incomplete or duplicated")
    ranks = [item.rank for item in result.results]
    if set(ranks) != set(range(1, len(expected) + 1)):
        raise ValueError("reranker ranks are incomplete")
    by_id = {item.offer.offer_id: item for item in candidates}
    ordered: list[RetrievalCandidate] = []
    for hit in sorted(result.results, key=lambda item: item.rank):
        if not math.isfinite(hit.relevance_score):
            raise ValueError("reranker returned non-finite score")
        candidate = by_id[hit.offer_id]
        ordered.append(
            candidate.model_copy(
                update={
                    "rerank_score": hit.relevance_score,
                    "rerank_version": result.model_version or result.model,
                }
            )
        )
    return ordered


def _build_rerank_query(query_text: str, constraints: ShoppingConstraints) -> str:
    parts = [_sanitize_query(query_text)]
    for name in ("category_name", "brand", "model", "colors", "platforms", "attributes"):
        value = constraints.effective_value(name)
        if value in (None, "", [], {}):
            continue
        if isinstance(value, dict):
            values = cast(dict[str, object], value)
            rendered = ", ".join(f"{key}:{values[key]}" for key in sorted(values))
        elif isinstance(value, list):
            items = cast(list[object], value)
            rendered = ", ".join(str(item) for item in items)
        else:
            rendered = str(value)
        parts.append(f"{name}: {_sanitize_query(rendered)}")
    return " ".join(part for part in parts if part).strip()


def _sanitize_query(value: str) -> str:
    value = re.sub(r"https?://\S+|\S+@\S+", " ", value, flags=re.IGNORECASE)
    value = re.sub(r"(?:owner|session|request)[_-]?id\s*[:=]\s*\S+", " ", value, flags=re.I)
    value = re.sub(r"(?:\+?\d[\d ()-]{7,}\d)", " ", value)
    return " ".join(value.split())


def _rerank_cache_key(identity: str, query: str, version: str, constraints_version: int) -> str:
    payload = {
        "identity": identity,
        "query": query,
        "candidate_version": version,
        "constraints_version": constraints_version,
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


__all__ = ["RetrievalService", "SearchAndCompareResult", "SearchOnceResult"]
