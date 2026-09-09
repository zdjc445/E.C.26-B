"""查询准备、批量执行与跨查询融合测试。"""

from __future__ import annotations

import hashlib
from typing import Any

import pytest

from shijiajing_agent.agent_runtime.contracts import AgentRuntimeUsage
from shijiajing_agent.contracts import (
    HardFilters,
    RetrievalCandidate,
    RetrievalQuery,
    ShoppingConstraints,
)
from shijiajing_agent.ports.reranker import RerankerStatus, RerankHit, RerankResult
from shijiajing_agent.ports.retrieval import RetrievalResult, record_retrieval_usage
from shijiajing_agent.rag_contracts import (
    ChannelKind,
    ChannelResult,
    ChannelStatus,
    PreparedQuery,
    QueryPlan,
    QuerySource,
)
from shijiajing_agent.services.retrieval import RetrievalService
from tests.unit.conftest import offer


def prepared(text: str) -> PreparedQuery:
    return PreparedQuery(
        query_id="q:" + hashlib.sha256(text.encode()).hexdigest()[:24],
        text=text,
        hard_filters=HardFilters(),
        constraints_version=1,
        source=QuerySource.ORIGINAL,
        fingerprint=hashlib.sha256(text.encode()).hexdigest(),
    )


class FakeRewrite:
    async def rewrite(self, text: str, constraints: Any, recognition: Any) -> QueryPlan:
        del text, constraints, recognition
        return QueryPlan(
            original_query=prepared("主查询"),
            variants=[prepared("English alias")],
        )


class FakeRetrieval:
    def __init__(self) -> None:
        self.queries: list[RetrievalQuery] = []

    async def setup(self) -> None:
        pass

    async def close(self) -> None:
        pass

    async def search(self, query: RetrievalQuery, **kwargs: Any) -> RetrievalResult:
        del kwargs
        self.queries.append(query)
        if query.query_text == "主查询":
            hits = [
                RetrievalCandidate(
                    offer=offer("shared"),
                    dense_text_score=1.0,
                    recall_score=1.0,
                )
            ]
        else:
            hits = [
                RetrievalCandidate(
                    offer=offer("shared"),
                    dense_text_score=0.9,
                    recall_score=0.9,
                ),
                RetrievalCandidate(
                    offer=offer("variant-only"),
                    dense_text_score=0.8,
                    recall_score=0.8,
                ),
            ]
        return RetrievalResult(
            candidates=hits,
            total_found=len(hits),
            channel_counts={"dense": len(hits)},
            channel_results=[
                ChannelResult(
                    query_id="q:adapter",
                    channel=ChannelKind.DENSE,
                    hits=hits,
                    status=ChannelStatus.SUCCESS,
                )
            ],
            channel_health={"dense": ChannelStatus.SUCCESS},
        )


class VersionedFakeRetrieval(FakeRetrieval):
    index_version = "manifest-v1"

    async def search(self, query: RetrievalQuery, **kwargs: Any) -> RetrievalResult:
        result = await super().search(query, **kwargs)
        result.index_version = self.index_version
        return result


class MeteredFakeRetrieval(FakeRetrieval):
    async def search(self, query: RetrievalQuery, **kwargs: Any) -> RetrievalResult:
        record_retrieval_usage(
            AgentRuntimeUsage(db_search_attempts=2, embedding_calls=1, embedding_inputs=1)
        )
        return await super().search(query, **kwargs)


class CountingReranker:
    model = "fake-reranker"
    model_version = "fake-reranker-v1"
    instruction_version = "product-semantic-v1"
    summary_version = "offer-summary-v1"
    tokenizer_version = "fake-tokenizer-v1"
    cache_identity = "fake-reranker-v1"
    document_max_tokens = 384

    def __init__(self, *, invalid: bool = False) -> None:
        self.calls = 0
        self.invalid = invalid

    async def setup(self) -> None:
        pass

    async def close(self) -> None:
        pass

    async def rerank(self, query: str, documents: list[Any], **kwargs: Any) -> RerankResult:
        del query
        self.calls += 1
        candidate_version = kwargs["candidate_version"]
        if self.invalid:
            hits = [RerankHit(offer_id=documents[0].offer_id, relevance_score=1.0, rank=1)]
        else:
            hits = [
                RerankHit(
                    offer_id=document.offer_id,
                    relevance_score=float(len(documents) - index),
                    rank=index + 1,
                )
                for index, document in enumerate(reversed(documents))
            ]
        return RerankResult(
            status=RerankerStatus.SUCCESS,
            results=hits,
            model=self.model,
            model_version=self.model_version,
            candidate_version=candidate_version,
            usage=AgentRuntimeUsage(reranker_requests=1, reranked_documents=len(documents)),
        )


@pytest.mark.asyncio
async def test_search_once_preserves_plan_versions_and_fuses_variants() -> None:
    retrieval = FakeRetrieval()
    service = RetrievalService(
        FakeRewrite(),
        retrieval,
        comparison=object(),  # type: ignore[arg-type]
        candidate_window_limit=10,
        initial_max_queries=3,
    )

    result = await service.search_once(
        "主查询",
        ShoppingConstraints(),
        constraints_version=4,
    )

    assert [query.query_text for query in retrieval.queries] == ["主查询", "English alias"]
    assert result.plan is not None
    assert result.plan.original_query.constraints_version == 4
    assert result.plan.variants[0].constraints_version == 4
    assert result.usage.model_calls == 1
    assert result.usage.retrieval_calls == 2
    assert {item.offer.offer_id for item in result.candidates} == {"shared", "variant-only"}
    shared = next(item for item in result.candidates if item.offer.offer_id == "shared")
    assert len(shared.query_ids) == 2
    assert result.retrieval.fusion_version == "best-query-channel-rrf-v1"


@pytest.mark.asyncio
async def test_search_once_reranks_once_and_reuses_cache() -> None:
    reranker = CountingReranker()
    service = RetrievalService(
        FakeRewrite(),
        FakeRetrieval(),
        comparison=object(),  # type: ignore[arg-type]
        candidate_window_limit=10,
        initial_max_queries=3,
        reranker=reranker,  # type: ignore[arg-type]
    )

    first = await service.search_once("主查询", ShoppingConstraints())
    second = await service.search_once("主查询", ShoppingConstraints())

    assert reranker.calls == 1
    assert first.usage.reranker_requests == 1
    assert second.usage.reranker_cache_hits == 1
    assert first.retrieval.rerank_version == "fake-reranker-v1"


@pytest.mark.asyncio
async def test_invalid_reranker_result_falls_back_to_rrf() -> None:
    reranker = CountingReranker(invalid=True)
    service = RetrievalService(
        FakeRewrite(),
        FakeRetrieval(),
        comparison=object(),  # type: ignore[arg-type]
        candidate_window_limit=10,
        reranker=reranker,  # type: ignore[arg-type]
    )

    result = await service.search_once("主查询", ShoppingConstraints())

    assert result.retrieval.rerank_result is not None
    assert result.retrieval.rerank_result.status is RerankerStatus.FAILED
    assert result.retrieval.rerank_result.fallback_reason == "service_result_validation_failed"
    assert all(item.rerank_score is None for item in result.candidates)


def test_prepared_query_fingerprint_binds_index_manifest() -> None:
    service = RetrievalService(
        FakeRewrite(),
        VersionedFakeRetrieval(),
        comparison=object(),  # type: ignore[arg-type]
        index_manifest_id="manifest-v1",
    )
    query = service._prepared_query(  # type: ignore[attr-defined]
        "同一查询",
        hard_filters=HardFilters(),
        soft_terms=[],
        negative_terms=[],
        constraints_version=1,
        source=QuerySource.ORIGINAL,
        index_manifest_id="manifest-v1",
    )
    other = service._prepared_query(  # type: ignore[attr-defined]
        "同一查询",
        hard_filters=HardFilters(),
        soft_terms=[],
        negative_terms=[],
        constraints_version=1,
        source=QuerySource.ORIGINAL,
        index_manifest_id="manifest-v2",
    )
    assert query.index_manifest_id == "manifest-v1"
    assert query.fingerprint != other.fingerprint


@pytest.mark.asyncio
async def test_prepared_query_rejects_mismatched_index_manifest() -> None:
    retrieval = VersionedFakeRetrieval()
    service = RetrievalService(
        FakeRewrite(), retrieval, comparison=object(), index_manifest_id="manifest-v2"
    )
    query = service._prepared_query(  # type: ignore[attr-defined]
        "查询",
        hard_filters=HardFilters(),
        soft_terms=[],
        negative_terms=[],
        constraints_version=1,
        source=QuerySource.ORIGINAL,
        index_manifest_id="manifest-v2",
    )
    with pytest.raises(ValueError, match="manifest"):
        await service.execute_prepared_query(query)


@pytest.mark.asyncio
async def test_retrieval_usage_separates_logical_and_physical_calls() -> None:
    service = RetrievalService(
        FakeRewrite(), MeteredFakeRetrieval(), comparison=object(), index_manifest_id="v1"
    )
    query = service._prepared_query(  # type: ignore[attr-defined]
        "查询",
        hard_filters=HardFilters(),
        soft_terms=[],
        negative_terms=[],
        constraints_version=1,
        source=QuerySource.ORIGINAL,
        index_manifest_id="v1",
    )

    result = await service.execute_prepared_query(query)

    assert result.usage.retrieval_calls == 1
    assert result.usage.db_search_attempts == 2
    assert result.usage.embedding_calls == 1
    assert result.usage.embedding_inputs == 1
