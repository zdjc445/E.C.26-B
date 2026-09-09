"""查询准备、批量执行与跨查询融合测试。"""

from __future__ import annotations

import hashlib
from typing import Any

import pytest

from shijiajing_agent.contracts import (
    HardFilters,
    RetrievalCandidate,
    RetrievalQuery,
    ShoppingConstraints,
)
from shijiajing_agent.ports.retrieval import RetrievalResult
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
