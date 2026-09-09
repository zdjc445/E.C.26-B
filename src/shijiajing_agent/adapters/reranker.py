"""阿里云百炼 Reranker 适配器。

供应商响应在这里解析和严格校验；上层只看到 RerankResult。云端失败返回完整失败结果，
由检索服务保留 RRF 顺序并继续处理，不把半份模型结果混入线上排序。
"""

from __future__ import annotations

import asyncio
import math
import time
from collections.abc import Mapping
from typing import Any, cast
from uuid import uuid4

import httpx

from shijiajing_agent.agent_runtime.contracts import AgentRuntimeUsage
from shijiajing_agent.config import Settings
from shijiajing_agent.domain.reranker_summary import (
    INSTRUCTION,
    INSTRUCTION_VERSION,
    SUMMARY_VERSION,
    Utf8TokenCounter,
    contains_sensitive_text,
)
from shijiajing_agent.ports.reranker import (
    RerankDocument,
    RerankerStatus,
    RerankHit,
    RerankResult,
    RerankTokenCounter,
)


class AliyunRerankerAdapter:
    """百炼 ``qwen3-rerank`` 的 HTTP 实现。"""

    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        token_counter: RerankTokenCounter | None = None,
    ) -> None:
        if not settings.reranker_base_url or not settings.reranker_api_key:
            raise ValueError(
                "Reranker 配置缺失，请设置 SHIJIAJING_RERANKER_BASE_URL / "
                "SHIJIAJING_RERANKER_API_KEY"
            )
        if not settings.reranker_model:
            raise ValueError("Reranker 配置缺失，请设置 SHIJIAJING_RERANKER_MODEL")
        if settings.reranker_provider != "aliyun_bailian":
            raise ValueError("当前只支持 RERANKER_PROVIDER=aliyun_bailian")
        self._settings = settings
        self._base_url = settings.reranker_base_url
        self._api_key = settings.reranker_api_key
        self.model = settings.reranker_model
        self.model_version = self.model
        self.document_max_tokens = settings.reranker_document_max_tokens
        self.instruction_version = INSTRUCTION_VERSION
        self.summary_version = SUMMARY_VERSION
        self._token_counter = token_counter or Utf8TokenCounter()
        self.tokenizer_version = self._token_counter.version
        self.cache_identity = ":".join(
            (
                self.model,
                self.model_version,
                self.instruction_version,
                self.summary_version,
                self.tokenizer_version,
            )
        )
        self._client = httpx.AsyncClient(transport=transport) if transport else httpx.AsyncClient()
        self._closed = False

    async def setup(self) -> None:
        """HTTP client在构造时准备；保留统一资源生命周期入口。"""

    async def close(self) -> None:
        if not self._closed:
            self._closed = True
            await self._client.aclose()

    async def rerank(
        self,
        query: str,
        documents: list[RerankDocument],
        *,
        top_k: int,
        deadline: float | None,
        candidate_version: str,
    ) -> RerankResult:
        started = time.perf_counter()
        if not documents:
            return self._result(
                status=RerankerStatus.SUCCESS,
                candidate_version=candidate_version,
                latency_ms=0.0,
            )
        if len(documents) > self._settings.reranker_max_documents:
            return self._failed(candidate_version, "document_limit_exceeded", started)
        if contains_sensitive_text(query) or any(
            contains_sensitive_text(item.text) for item in documents
        ):
            return self._failed(candidate_version, "unsafe_input", started, len(documents))
        if any(
            item.token_count > self._settings.reranker_document_max_tokens for item in documents
        ):
            return self._failed(
                candidate_version, "document_token_limit_exceeded", started, len(documents)
            )
        query = self._token_counter.truncate(
            query.strip(), self._settings.reranker_query_max_tokens
        )
        if not query:
            return self._failed(candidate_version, "empty_query", started, len(documents))
        total_input_tokens = self._token_counter.count(query) * len(documents) + sum(
            item.token_count for item in documents
        )
        if total_input_tokens > self._settings.reranker_request_max_tokens:
            return self._failed(
                candidate_version, "request_token_limit_exceeded", started, len(documents)
            )

        payload = {
            "model": self.model,
            "query": query,
            "documents": [item.text for item in documents],
            "top_n": len(documents),
            "instruct": INSTRUCTION,
        }
        transient_statuses = {408, 409, 425, 429, 500, 502, 503, 504}
        attempts = max(1, self._settings.reranker_max_attempts)
        response: httpx.Response | None = None
        request_id = uuid4().hex  # 只用于本次请求追踪，不进入 payload 或结果。
        for attempt in range(attempts):
            timeout = self._request_timeout(deadline)
            if timeout <= 0:
                return self._failed(candidate_version, "deadline_exceeded", started, len(documents))
            try:
                response = await self._client.post(
                    self._base_url,
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                        "X-Request-ID": request_id,
                    },
                    json=payload,
                    timeout=timeout,
                )
                if response.status_code not in transient_statuses:
                    break
            except (httpx.TimeoutException, httpx.NetworkError):
                response = None
            if attempt + 1 < attempts:
                await asyncio.sleep(0.02 * (2**attempt))
        if response is None:
            return self._failed(candidate_version, "network_or_timeout", started, len(documents))
        if response.status_code >= 400:
            return self._failed(
                candidate_version, f"http_{response.status_code}", started, len(documents)
            )
        try:
            body = response.json()
        except ValueError:
            return self._failed(candidate_version, "invalid_json", started, len(documents))
        try:
            hits, response_model, input_tokens, output_tokens = self._parse_response(
                body, documents
            )
        except ValueError as exc:
            return self._failed(candidate_version, str(exc), started, len(documents))
        total_tokens = input_tokens + output_tokens
        latency_ms = (time.perf_counter() - started) * 1000
        return self._result(
            status=RerankerStatus.SUCCESS,
            candidate_version=candidate_version,
            results=hits,
            model=response_model or self.model,
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            truncated_documents=sum(item.truncated for item in documents),
        )

    def _request_timeout(self, deadline: float | None) -> float:
        configured = self._settings.reranker_timeout_seconds
        return configured if deadline is None else min(configured, max(0.0, deadline))

    @staticmethod
    def _parse_response(
        body: Any, documents: list[RerankDocument]
    ) -> tuple[list[RerankHit], str | None, int, int]:
        if not isinstance(body, Mapping):
            raise ValueError("invalid_response_shape")
        body_map = cast(dict[str, Any], body)
        raw_results_value = body_map.get("results")
        if not isinstance(raw_results_value, list):
            raise ValueError("incomplete_results")
        raw_results = cast(list[object], raw_results_value)
        if len(raw_results) != len(documents):
            raise ValueError("incomplete_results")
        by_index: dict[int, float] = {}
        for raw_item in raw_results:
            if not isinstance(raw_item, Mapping):
                raise ValueError("invalid_result_item")
            item = cast(dict[str, object], raw_item)
            index = item.get("index")
            score = item.get("relevance_score")
            if not isinstance(index, int) or index < 0 or index >= len(documents):
                raise ValueError("unknown_result_index")
            if index in by_index or not isinstance(score, (int, float)) or not math.isfinite(score):
                raise ValueError("invalid_result_score")
            by_index[index] = float(score)
        if set(by_index) != set(range(len(documents))):
            raise ValueError("missing_result_index")
        ordered = sorted(by_index.items(), key=lambda pair: (-pair[1], pair[0]))
        hits = [
            RerankHit(
                offer_id=documents[index].offer_id,
                relevance_score=score,
                rank=rank,
            )
            for rank, (index, score) in enumerate(ordered, start=1)
        ]
        usage = body_map.get("usage")
        usage_map = cast(dict[str, Any], usage) if isinstance(usage, Mapping) else {}
        total_tokens = int(usage_map.get("total_tokens", 0))
        input_tokens = int(usage_map.get("prompt_tokens", total_tokens))
        if total_tokens < input_tokens:
            total_tokens = input_tokens
        return (
            hits,
            _as_optional_str(body_map.get("model")),
            input_tokens,
            total_tokens - input_tokens,
        )

    def _failed(
        self, candidate_version: str, reason: str, started: float, document_count: int = 0
    ) -> RerankResult:
        return self._result(
            status=RerankerStatus.FAILED,
            candidate_version=candidate_version,
            fallback_reason=reason,
            latency_ms=(time.perf_counter() - started) * 1000,
            truncated_documents=0,
            reranked_documents=document_count,
        )

    def _result(self, **kwargs: Any) -> RerankResult:
        status = kwargs.get("status", RerankerStatus.FAILED)
        input_tokens = int(kwargs.get("input_tokens", 0))
        output_tokens = int(kwargs.get("output_tokens", 0))
        total_tokens = int(kwargs.get("total_tokens", input_tokens + output_tokens))
        requests = (
            1
            if kwargs.get("candidate_version")
            and (status is not RerankerStatus.SUCCESS or kwargs.get("results") is not None)
            else 0
        )
        # 空候选是成功的本地短路，不消耗供应商请求。
        if status is RerankerStatus.SUCCESS and not kwargs.get("results"):
            requests = 0
        reranked_documents = int(kwargs.get("reranked_documents", len(kwargs.get("results", []))))
        usage = AgentRuntimeUsage(
            reranker_requests=requests,
            reranked_documents=reranked_documents,
            reranker_input_tokens=input_tokens,
            reranker_output_tokens=output_tokens,
            reranker_total_tokens=total_tokens,
            reranker_latency_ms=float(kwargs.get("latency_ms", 0.0)),
            reranker_estimated_cost=total_tokens
            / 1_000_000
            * self._settings.reranker_cost_per_million_tokens,
            reranker_truncated_documents=int(kwargs.get("truncated_documents", 0)),
            reranker_fallbacks=1 if status is not RerankerStatus.SUCCESS else 0,
        )
        payload = dict(kwargs)
        payload.pop("reranked_documents", None)
        payload.update(
            {
                "model": kwargs.get("model", self.model),
                "model_version": self.model_version,
                "instruction_version": self.instruction_version,
                "summary_version": self.summary_version,
                "tokenizer_version": self.tokenizer_version,
                "usage": usage,
            }
        )
        return RerankResult(**payload)


class FakeReranker:
    """开发/单测显式依赖：确定性分数，不代表真实模型质量。"""

    model = "fake-reranker"
    model_version = "fake-reranker-v1"
    instruction_version = INSTRUCTION_VERSION
    summary_version = SUMMARY_VERSION
    tokenizer_version = "fake-tokenizer-v1"
    cache_identity = "fake-reranker-v1"

    async def setup(self) -> None:
        pass

    async def close(self) -> None:
        pass

    async def rerank(
        self,
        query: str,
        documents: list[RerankDocument],
        *,
        top_k: int,
        deadline: float | None,
        candidate_version: str,
    ) -> RerankResult:
        del deadline
        query_terms = {term.lower() for term in query.split() if term}
        scored = [
            (document, sum(term in document.text.lower() for term in query_terms))
            for document in documents
        ]
        scored.sort(key=lambda item: (-item[1], item[0].offer_id))
        results = [
            RerankHit(offer_id=document.offer_id, relevance_score=float(score), rank=rank)
            for rank, (document, score) in enumerate(scored[:top_k], start=1)
        ]
        return RerankResult(
            status=RerankerStatus.SUCCESS,
            results=results,
            model=self.model,
            model_version=self.model_version,
            instruction_version=self.instruction_version,
            summary_version=self.summary_version,
            tokenizer_version=self.tokenizer_version,
            candidate_version=candidate_version,
            usage=AgentRuntimeUsage(
                reranker_requests=0,
                reranked_documents=len(documents),
            ),
        )


def _as_optional_str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


__all__ = ["AliyunRerankerAdapter", "FakeReranker"]
