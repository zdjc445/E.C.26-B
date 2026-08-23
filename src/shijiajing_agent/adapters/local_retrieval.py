"""本地词法检索降级适配器。

- 使用与 Milvus 相同的只读商品快照（JSONL，每行一个 Offer）。
- 执行相同的硬过滤（``offer_matches_hard_filters``，与 Milvus filter 表达式同语义）。
- BM25 词法得分排序；dense 信号缺失时如实为 None，不做伪向量。
- 输出领域协议 ``RetrievalResult``，不声称执行了向量检索。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from shijiajing_agent.adapters.lexical import Bm25Index, tokenize
from shijiajing_agent.contracts import Offer, RetrievalCandidate, RetrievalQuery
from shijiajing_agent.domain.filters import offer_matches_hard_filters
from shijiajing_agent.errors import RetrievalUnavailableError
from shijiajing_agent.ports.observability import MetricsPort
from shijiajing_agent.ports.retrieval import RetrievalResult


class LocalLexicalRetrievalAdapter:
    """BM25 本地词法检索（ProductRetrievalPort 降级实现）。"""

    def __init__(self, snapshot_path: Path, *, metrics: MetricsPort | None = None) -> None:
        self._path = Path(snapshot_path)
        self._metrics = metrics
        self._loaded: tuple[list[Offer], Bm25Index, str] | None = None

    async def setup(self) -> None:
        """本地快照没有外部连接；保留统一 runtime 生命周期入口。"""

    async def close(self) -> None:
        """释放惰性索引引用，保证 runtime 关闭后不保留快照对象。"""
        self._loaded = None

    # ------------------------------------------------------------------
    def _load(self) -> tuple[list[Offer], Bm25Index, str]:
        """惰性加载只读快照并构建 BM25 索引。"""
        if self._loaded is not None:
            return self._loaded
        if not self._path.exists():
            raise RetrievalUnavailableError(
                f"本地商品快照不可用：{self._path}（设置 SHIJIAJING_LOCAL_PRODUCT_SNAPSHOT_PATH）"
            )
        offers: list[Offer] = []
        texts: list[str] = []
        try:
            with self._path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    offer = Offer.model_validate_json(line)
                    offers.append(offer)
                    texts.append(offer.search_text or _fallback_text(offer))
        except (json.JSONDecodeError, ValueError) as exc:
            raise RetrievalUnavailableError(f"本地商品快照解析失败：{exc}") from exc
        digest = _snapshot_digest(self._path, len(offers))
        index = Bm25Index(texts)
        self._loaded = (offers, index, digest)
        return self._loaded

    # ------------------------------------------------------------------
    async def search(
        self,
        query: RetrievalQuery,
        *,
        image: Any = None,
        top_k: int = 100,
        union_limit: int = 200,
        category_names: dict[str, str] | None = None,
    ) -> RetrievalResult:
        del image, union_limit, category_names  # 本地降级：无图像通道；union_limit 不适用
        offers, index, digest = self._load()
        query_tokens = tokenize(query.query_text)
        hits = index.score(query_tokens)
        filtered: list[tuple[Offer, float]] = []
        for doc_idx, bm25 in hits:
            offer = offers[doc_idx]
            if offer_matches_hard_filters(offer, query.hard_filters):
                filtered.append((offer, bm25))
        filtered.sort(key=lambda pair: pair[1], reverse=True)
        filtered = filtered[:top_k]
        total_found = len(filtered)

        scores = [s for _, s in filtered]
        max_s = max(scores, default=0.0)
        min_s = min(scores, default=0.0)
        span = max_s - min_s if max_s > min_s else 1.0

        candidates: list[RetrievalCandidate] = []
        for offer, bm25 in filtered:
            sparse_norm = (bm25 - min_s) / span if bm25 > 0 else 0.0
            candidates.append(
                RetrievalCandidate(
                    offer=offer,
                    dense_text_score=None,
                    sparse_score=sparse_norm,
                    metadata_match=metadata_match(query, offer),
                    recall_score=sparse_norm,
                    channel_sources=["sparse"],
                )
            )
        if self._metrics is not None:
            self._metrics.inc("retrieval_candidate_count", value=float(len(candidates)))
            if not candidates:
                self._metrics.inc("retrieval_zero_result_rate")
        return RetrievalResult(
            candidates=candidates,
            total_found=total_found,
            channel_counts={"sparse": len(candidates)},
            index_version=digest,
            fusion_version="weighted-v1",
        )


def _fallback_text(offer: Offer) -> str:
    """快照缺少 search_text 时（如手工维护的快照）的保守拼接。"""
    parts = [
        offer.category_id or "",
        offer.brand or "",
        offer.model or "",
        offer.title or "",
    ]
    for key, value in {**offer.identity_attributes, **offer.variant_attributes}.items():
        parts.append(f"{key} {value}")
    return " ".join(p for p in parts if p)


def metadata_match(query: RetrievalQuery, offer: Offer) -> float:
    """软词命中率：query_text 与 soft_terms 的 token 中，出现在 offer 检索文本的比例。"""
    text = (offer.search_text or _fallback_text(offer)).lower()
    terms = [*tokenize(query.query_text), *(t.lower() for t in query.soft_terms)]
    terms = list(dict.fromkeys(terms))
    if not terms:
        return 1.0
    hit = sum(1 for t in terms if t in text)
    return hit / len(terms)


def _snapshot_digest(path: Path, n_lines: int) -> str:
    """快照版本指纹：mtime + 行数哈希，进入 RetrievalResult.index_version。"""
    stat = path.stat()
    return hashlib.sha256(f"{stat.st_mtime_ns}:{n_lines}".encode()).hexdigest()[:12]
