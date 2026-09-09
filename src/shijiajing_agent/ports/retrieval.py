"""检索 Port（方案 §4.1、§13）。

ProductRetrievalPort 的 Milvus 与本地降级实现返回同一领域协议。
"""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass
from dataclasses import field as dc_field
from typing import Protocol

from shijiajing_agent.agent_runtime.contracts import AgentRuntimeUsage
from shijiajing_agent.contracts import ImageRef, RetrievalCandidate, RetrievalQuery
from shijiajing_agent.ports.lifecycle import ResourceLifecyclePort
from shijiajing_agent.rag_contracts import ChannelResult, ChannelStatus


@dataclass
class RetrievalResult:
    candidates: list[RetrievalCandidate]
    total_found: int = 0
    fallback_used: bool = False
    fallback_reason: str | None = None
    channel_counts: dict[str, int] = dc_field(default_factory=dict[str, int])
    index_version: str | None = None
    fusion_version: str | None = None
    rerank_version: str | None = None
    channel_results: list[ChannelResult] = dc_field(default_factory=list[ChannelResult])
    channel_health: dict[str, ChannelStatus] = dc_field(default_factory=dict[str, ChannelStatus])
    selected_candidates: list[RetrievalCandidate] = dc_field(
        default_factory=list[RetrievalCandidate]
    )
    truncated_count: int = 0
    usage: AgentRuntimeUsage = dc_field(default_factory=AgentRuntimeUsage)


_RETRIEVAL_USAGE: ContextVar[AgentRuntimeUsage | None] = ContextVar(
    "shijiajing_retrieval_usage", default=None
)


def begin_retrieval_usage() -> Token[AgentRuntimeUsage | None]:
    """开始一次逻辑查询的物理调用计量上下文。"""
    return _RETRIEVAL_USAGE.set(AgentRuntimeUsage())


def record_retrieval_usage(usage: AgentRuntimeUsage) -> None:
    """由 embedding/数据库适配器在真实调用边界记录物理用量。"""
    current = _RETRIEVAL_USAGE.get()
    if current is not None:
        _RETRIEVAL_USAGE.set(current.add(usage))


def finish_retrieval_usage(token: Token[AgentRuntimeUsage | None]) -> AgentRuntimeUsage:
    usage = _RETRIEVAL_USAGE.get() or AgentRuntimeUsage()
    _RETRIEVAL_USAGE.reset(token)
    return usage


class ProductRetrievalPort(ResourceLifecyclePort, Protocol):
    """混合召回。dense + sparse/BM25 + metadata filter（+image similarity）。"""

    async def search(
        self,
        query: RetrievalQuery,
        *,
        image: ImageRef | None = None,
        top_k: int = 100,
        union_limit: int = 200,
        category_names: dict[str, str] | None = None,
    ) -> RetrievalResult: ...


__all__ = [
    "ProductRetrievalPort",
    "RetrievalResult",
    "begin_retrieval_usage",
    "finish_retrieval_usage",
    "record_retrieval_usage",
]
