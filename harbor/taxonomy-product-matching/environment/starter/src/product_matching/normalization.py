"""Taxonomy 驱动的 Offer 标准化。"""

from __future__ import annotations

from collections.abc import Mapping

from product_matching.models import NormalizedCandidate, Offer
from product_matching.taxonomy import Taxonomy


class TaxonomyNormalizer:
    def __init__(self, taxonomy: Taxonomy) -> None:
        self._taxonomy = taxonomy

    def normalize_offer(self, offer: Offer) -> NormalizedCandidate:
        raise NotImplementedError("实现 Offer 标准化与失败记录")

    def normalize_recognition(
        self,
        *,
        category_id: str | None,
        brand: str | None,
        model: str | None,
        attributes: Mapping[str, str] | None,
    ) -> dict[str, object]:
        raise NotImplementedError("实现识别结果标准化")

    def _normalize_attribute(self, category_id: str | None, key: str, raw: str) -> str | None:
        raise NotImplementedError("实现属性标准化、单位换算与 enum 校验")

    @staticmethod
    def model_equivalent(a: str, b: str) -> bool:
        raise NotImplementedError("实现型号等价比较")

    @staticmethod
    def title_token_similarity(a: str, b: str) -> float:
        raise NotImplementedError("实现标题 token 相似度")
