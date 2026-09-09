"""Reranker 端口及其供应商无关的严格契约。

检索服务只依赖本模块；供应商请求格式、鉴权和响应解析留在 adapters/。
"""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from shijiajing_agent.agent_runtime.contracts import AgentRuntimeUsage
from shijiajing_agent.ports.lifecycle import ResourceLifecyclePort


class RerankerStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"
    FALLBACK = "fallback"


class RerankDocument(BaseModel):
    """发送给模型的安全商品摘要；不能携带来源引用或请求身份。"""

    model_config = ConfigDict(extra="forbid")

    offer_id: str = Field(min_length=1, max_length=256)
    text: str = Field(min_length=1, max_length=16_384)
    token_count: int = Field(ge=1)
    truncated: bool = False


class RerankHit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    offer_id: str = Field(min_length=1, max_length=256)
    relevance_score: float
    rank: int = Field(ge=1)


class RerankResult(BaseModel):
    """一次完整精排调用的可审计结果，不保存商品正文。"""

    model_config = ConfigDict(extra="forbid")

    status: RerankerStatus
    results: list[RerankHit] = Field(default_factory=list[RerankHit], max_length=200)
    model: str | None = Field(default=None, max_length=256)
    model_version: str | None = Field(default=None, max_length=256)
    instruction_version: str = Field(default="product-semantic-v1", max_length=128)
    summary_version: str = Field(default="offer-summary-v1", max_length=128)
    tokenizer_version: str = Field(default="utf8-estimator-v1", max_length=128)
    candidate_version: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    latency_ms: float = Field(default=0.0, ge=0)
    estimated_cost: float = Field(default=0.0, ge=0)
    truncated_documents: int = Field(default=0, ge=0)
    fallback_reason: str | None = Field(default=None, max_length=128)
    cache_hit: bool = False
    usage: AgentRuntimeUsage = Field(default_factory=AgentRuntimeUsage)


class RerankerPort(ResourceLifecyclePort, Protocol):
    """对当前 RRF 候选集执行一次固定模型精排。"""

    model: str
    model_version: str
    instruction_version: str
    summary_version: str
    tokenizer_version: str
    cache_identity: str

    async def rerank(
        self,
        query: str,
        documents: list[RerankDocument],
        *,
        top_k: int,
        deadline: float | None,
        candidate_version: str,
    ) -> RerankResult: ...


class RerankTokenCounter(Protocol):
    """与部署模型绑定的 Token 计数器；摘要构造不得按字符数猜测。"""

    version: str

    def count(self, text: str) -> int: ...

    def truncate(self, text: str, max_tokens: int) -> str: ...


__all__ = [
    "RerankDocument",
    "RerankHit",
    "RerankResult",
    "RerankTokenCounter",
    "RerankerPort",
    "RerankerStatus",
]
