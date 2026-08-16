"""同款候选、硬冲突评分与 complete-link 聚类。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from product_matching.models import NormalizedCandidate, Offer, PairResult
from product_matching.taxonomy import Taxonomy


@dataclass(frozen=True)
class PairSimilarityProviders:
    title: Callable[[str, str], float]
    image: Callable[[Offer, Offer], float | None] | None = None


class SameItemMatcher:
    def __init__(
        self,
        taxonomy: Taxonomy,
        providers: PairSimilarityProviders,
        *,
        accept_threshold: float = 0.82,
        review_threshold: float = 0.68,
    ) -> None:
        self._taxonomy = taxonomy
        self._providers = providers
        self._accept = accept_threshold
        self._review = review_threshold

    def generate_candidates(self, candidates: list[NormalizedCandidate]) -> list[tuple[int, int]]:
        raise NotImplementedError("实现同款候选对生成")

    def judge_pair(self, a: NormalizedCandidate, b: NormalizedCandidate) -> PairResult:
        raise NotImplementedError("实现硬冲突、加权评分与结论")

    def cluster(
        self, candidates: list[NormalizedCandidate], pairs: list[tuple[int, int]]
    ) -> list[list[int]]:
        raise NotImplementedError("实现 complete-link 聚类")
