"""检索 Port（方案 §4.1、§13）。

ProductRetrievalPort 的 Milvus 与本地降级实现返回同一领域协议。
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field as dc_field
from typing import Protocol

from shijiajing_agent.contracts import ImageRef, RetrievalCandidate, RetrievalQuery


@dataclass
class RetrievalResult:
    candidates: list[RetrievalCandidate]
    total_found: int = 0
    fallback_used: bool = False
    fallback_reason: str | None = None
    channel_counts: dict[str, int] = dc_field(default_factory=dict[str, int])
    index_version: str | None = None


class ProductRetrievalPort(Protocol):
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
