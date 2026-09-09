"""可替换的召回融合策略；不改变同款、SKU 和最终业务排序。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import ClassVar, Protocol

from shijiajing_agent.contracts import RetrievalCandidate


class RetrievalFusionStrategy(Protocol):
    version: str

    def fuse(
        self, channel_results: dict[str, list[RetrievalCandidate]], limit: int
    ) -> list[RetrievalCandidate]: ...


class WeightedScoreFusion:
    """与 Milvus 适配器现有公式一致的兼容基线。

    调用方必须先完成各通道的 min-max 归一化；本策略只负责按可用通道
    重新归一化权重并生成 ``recall_score``。
    """

    version = "weighted-v1"
    _TEXT_WEIGHTS: ClassVar[dict[str, float]] = {
        "dense": 0.50,
        "sparse": 0.30,
        "metadata": 0.20,
    }
    _IMAGE_WEIGHTS: ClassVar[dict[str, float]] = {
        "dense": 0.35,
        "sparse": 0.20,
        "image": 0.25,
        "metadata": 0.20,
    }

    def fuse(
        self, channel_results: dict[str, list[RetrievalCandidate]], limit: int
    ) -> list[RetrievalCandidate]:
        merged: dict[str, RetrievalCandidate] = {}
        for candidates in channel_results.values():
            for candidate in candidates:
                merged.setdefault(candidate.offer.offer_id, candidate)
        image_channel = any(candidate.image_similarity is not None for candidate in merged.values())
        weights = self._IMAGE_WEIGHTS if image_channel else self._TEXT_WEIGHTS
        scored: list[RetrievalCandidate] = []
        for candidate in merged.values():
            scores = {
                "dense": candidate.dense_text_score,
                "sparse": candidate.sparse_score,
                "image": candidate.image_similarity,
                "metadata": candidate.metadata_match,
            }
            used = 0.0
            denominator = 0.0
            for channel, weight in weights.items():
                score = scores[channel]
                if score is not None:
                    used += weight * score
                    denominator += weight
            recall_score = used / denominator if denominator else 0.0
            scored.append(candidate.model_copy(update={"recall_score": recall_score}))
        return sorted(
            scored,
            key=lambda candidate: (-candidate.recall_score, candidate.offer.offer_id),
        )[:limit]


class ReciprocalRankFusion:
    def __init__(self, k: int = 60) -> None:
        if k < 1:
            raise ValueError("RRF k 必须大于 0")
        self.k = k
        self.version = f"rrf-v1-k{k}"

    def fuse(
        self, channel_results: dict[str, list[RetrievalCandidate]], limit: int
    ) -> list[RetrievalCandidate]:
        scores: dict[str, float] = {}
        candidates: dict[str, RetrievalCandidate] = {}
        for channel in sorted(channel_results):
            for rank, candidate in enumerate(channel_results[channel], start=1):
                offer_id = candidate.offer.offer_id
                candidates.setdefault(offer_id, candidate)
                scores[offer_id] = scores.get(offer_id, 0.0) + 1.0 / (self.k + rank)
        return sorted(
            candidates.values(),
            key=lambda candidate: (-scores[candidate.offer.offer_id], candidate.offer.offer_id),
        )[:limit]


class BestQueryChannelRRF:
    """生产固定融合：每个通道只取同一 Offer 的最佳查询名次。"""

    version = "best-query-channel-rrf-v1"

    def __init__(self, k: int = 60) -> None:
        if k < 1:
            raise ValueError("RRF k 必须大于 0")
        self.k = k

    def fuse(
        self,
        query_channels: Mapping[str, Mapping[str, Sequence[RetrievalCandidate]]],
        limit: int,
        *,
        usable_channels: Sequence[str] | None = None,
    ) -> list[RetrievalCandidate]:
        """按 ``max_q(1/(k+rank))`` 融合，成功但零命中的通道仍计入权重。"""
        usable = (
            set(usable_channels)
            if usable_channels is not None
            else {channel for channels in query_channels.values() for channel in channels}
        )
        if not usable:
            return []
        weights = 1.0 / len(usable)
        best_scores: dict[str, dict[str, float]] = {}
        candidates: dict[str, RetrievalCandidate] = {}
        for _query_id, channels in query_channels.items():
            for channel, ranked in channels.items():
                if channel not in usable:
                    continue
                seen: set[str] = set()
                for rank, candidate in enumerate(ranked, start=1):
                    offer_id = candidate.offer.offer_id
                    if offer_id in seen:
                        continue
                    seen.add(offer_id)
                    existing = candidates.get(offer_id)
                    if existing is None:
                        candidates[offer_id] = candidate.model_copy(
                            update={
                                "channel_sources": list(
                                    dict.fromkeys([*candidate.channel_sources, channel])
                                )
                            }
                        )
                    else:
                        candidates[offer_id] = existing.model_copy(
                            update={
                                "query_ids": list(
                                    dict.fromkeys([*existing.query_ids, *candidate.query_ids])
                                ),
                                "channel_sources": list(
                                    dict.fromkeys(
                                        [
                                            *existing.channel_sources,
                                            *candidate.channel_sources,
                                            channel,
                                        ]
                                    )
                                ),
                            }
                        )
                    per_channel = best_scores.setdefault(offer_id, {})
                    score = 1.0 / (self.k + rank)
                    per_channel[channel] = max(per_channel.get(channel, 0.0), score)
        scored = [
            candidate.model_copy(
                update={
                    "recall_score": weights
                    * sum(best_scores.get(candidate.offer.offer_id, {}).values())
                }
            )
            for candidate in candidates.values()
        ]
        return sorted(
            scored,
            key=lambda candidate: (-candidate.recall_score, candidate.offer.offer_id),
        )[:limit]
