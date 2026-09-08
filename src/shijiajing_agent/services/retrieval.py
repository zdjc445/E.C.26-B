"""一次检索工具与检索-比较组合工具。"""

from __future__ import annotations

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
from shijiajing_agent.domain.filters import HardFilterBuilder
from shijiajing_agent.ports.models import QueryRewritePort
from shijiajing_agent.ports.retrieval import ProductRetrievalPort, RetrievalResult
from shijiajing_agent.services.comparison import ComparisonResult, ComparisonService


@dataclass(frozen=True)
class SearchOnceResult:
    query: RetrievalQuery
    candidates: list[RetrievalCandidate]
    retrieval: RetrievalResult
    usage: AgentRuntimeUsage


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
    ) -> None:
        self._query_rewrite = query_rewrite
        self._retrieval = retrieval
        self._comparison = comparison
        self._category_names = category_names or {}
        self._top_k = top_k
        self._union_limit = union_limit

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
    ) -> SearchOnceResult:
        hard_filters = HardFilterBuilder().build(constraints)
        try:
            query = await self._query_rewrite.rewrite(query_text, constraints, recognition)
            if query.hard_filters != hard_filters:
                query = query.model_copy(update={"hard_filters": hard_filters})
            if soft_terms:
                query = query.model_copy(
                    update={"soft_terms": list(dict.fromkeys([*query.soft_terms, *soft_terms]))}
                )
        except Exception:
            query = RetrievalQuery(
                query_text=query_text,
                hard_filters=hard_filters if hard_filters else HardFilters(),
                soft_terms=list(dict.fromkeys(soft_terms or [])),
            )
        result = await self._retrieval.search(
            query,
            image=image,
            top_k=top_k or self._top_k,
            union_limit=union_limit or self._union_limit,
            category_names=self._category_names,
        )
        return SearchOnceResult(
            query=query,
            candidates=result.candidates,
            retrieval=result,
            usage=AgentRuntimeUsage(retrieval_calls=1),
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
    ) -> SearchAndCompareResult:
        search = await self.search_once(
            query_text,
            constraints,
            recognition=recognition,
            image=image,
            soft_terms=soft_terms,
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
                retrieval_calls=comparison.model_calls,
            )
        )
        return SearchAndCompareResult(search=search, comparison=comparison, usage=usage)


__all__ = ["RetrievalService", "SearchAndCompareResult", "SearchOnceResult"]
