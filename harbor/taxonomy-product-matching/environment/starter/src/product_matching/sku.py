"""SKU 拆分、报价去重与价格聚合。"""

from __future__ import annotations

from product_matching.models import NormalizedCandidate, SkuGroup
from product_matching.taxonomy import Taxonomy


class SkuSplitter:
    def __init__(self, taxonomy: Taxonomy) -> None:
        self._taxonomy = taxonomy

    def split_spu(
        self,
        spu_members: list[NormalizedCandidate],
        spu_id: str,
    ) -> list[SkuGroup]:
        raise NotImplementedError("实现 SKU 拆分、去重、价格聚合与风险标记")


def spu_id_for(members: list[NormalizedCandidate]) -> str:
    raise NotImplementedError("实现稳定 SPU ID")
