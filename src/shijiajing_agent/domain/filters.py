"""元数据硬过滤构建与零结果放宽。

- 用户明确修正或明确输入的 brand/model 进入硬过滤。
- 图片识别的品牌只有字段置信度 ≥ BRAND_HARD_FILTER_CONFIDENCE 才作为硬过滤；
  型号只有 ≥ MODEL_HARD_FILTER_CONFIDENCE 才作为硬过滤，低于阈值只计入软匹配。
- 零结果放宽只允许放宽图片识别产生且未被用户锁定的字段，顺序固定，最多一次。
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field as dc_field

from shijiajing_agent.contracts import (
    ConstraintSource,
    HardFilters,
    Offer,
    RetrievalQuery,
    ShoppingConstraints,
)


def offer_matches_hard_filters(offer: Offer, hf: HardFilters) -> bool:
    """硬过滤谓词：Milvus filter 表达式与本地词法降级共用同一语义。

    价格一律按 ``price`` 字段比较（运费/优惠为 null 时无法统一计算应付价，
    与 Milvus filter 表达式保持一致，见 adapters/milvus_retrieval.py）。
    """
    if hf.category_id and offer.category_id != hf.category_id:
        return False
    if offer.price is None:
        if hf.min_price is not None or hf.max_price is not None:
            return False
    else:
        if hf.min_price is not None and offer.price < hf.min_price:
            return False
        if hf.max_price is not None and offer.price > hf.max_price:
            return False
    if hf.platforms and (offer.platform not in hf.platforms):
        return False
    if hf.min_rating is not None and (offer.rating is None or offer.rating < hf.min_rating):
        return False
    if hf.brand and offer.brand != hf.brand:
        return False
    if hf.model and offer.model != hf.model:
        return False
    return True


@dataclass
class RelaxationResult:
    query: RetrievalQuery
    relaxed_fields: list[str] = dc_field(default_factory=list[str])
    notices: list[str] = dc_field(default_factory=list[str])


class HardFilterBuilder:
    def __init__(
        self,
        *,
        brand_confidence_threshold: float = 0.85,
        model_confidence_threshold: float = 0.90,
    ) -> None:
        self._brand_threshold = brand_confidence_threshold
        self._model_threshold = model_confidence_threshold

    def build(self, constraints: ShoppingConstraints) -> HardFilters:
        """元数据硬过滤。"""
        hf = HardFilters(category_id=constraints.category_id.value)
        hf.min_price = constraints.min_price.value
        hf.max_price = constraints.max_price.value
        if constraints.platforms.value:
            hf.platforms = list(constraints.platforms.value)
        hf.min_rating = constraints.min_rating.value

        hf.brand = self._brand_as_hard(constraints)
        hf.model = self._model_as_hard(constraints)
        return hf

    def _brand_as_hard(self, constraints: ShoppingConstraints) -> str | None:
        brand_sv = constraints.brand
        if not brand_sv.value:
            return None
        if brand_sv.source in (
            ConstraintSource.USER_CORRECTION,
            ConstraintSource.USER_TEXT,
            ConstraintSource.SELECTED_OPTION,
        ):
            return brand_sv.value
        if brand_sv.source == ConstraintSource.VISION:
            return brand_sv.value if brand_sv.confidence >= self._brand_threshold else None
        return None

    def _model_as_hard(self, constraints: ShoppingConstraints) -> str | None:
        model_sv = constraints.model
        if not model_sv.value:
            return None
        if model_sv.source in (
            ConstraintSource.USER_CORRECTION,
            ConstraintSource.USER_TEXT,
            ConstraintSource.SELECTED_OPTION,
        ):
            return model_sv.value
        if model_sv.source == ConstraintSource.VISION:
            return model_sv.value if model_sv.confidence >= self._model_threshold else None
        return None

    def relax(self, query: RetrievalQuery, constraints: ShoppingConstraints) -> RelaxationResult:
        """零结果放宽：只放宽图片识别产生且未被用户锁定的字段，顺序固定。"""
        relaxed: list[str] = []
        notices: list[str] = []
        hf = query.hard_filters.model_copy(deep=True)

        def _can_relax(field: str) -> bool:
            if field not in ("brand", "model", "attributes"):
                return False
            sv = getattr(constraints, field)
            if sv.source == ConstraintSource.VISION and not sv.locked_by_user:
                return True
            # attributes 单独判断：识别属性且未锁定
            if (
                field == "attributes"
                and sv.source == ConstraintSource.VISION
                and not sv.locked_by_user
            ):
                return True
            return False

        # 1. 移除识别型号硬过滤，保留为软关键词
        if hf.model and _can_relax("model"):
            soft = hf.model
            hf.model = None
            if soft not in query.soft_terms:
                query.soft_terms.append(soft)
            relaxed.append("model")
            notices.append(f"已放宽图片识别的型号条件（{soft}），保留为搜索关键词")
        # 2. 移除识别品牌硬过滤，保留为软关键词
        if hf.brand and _can_relax("brand"):
            soft = hf.brand
            hf.brand = None
            if soft not in query.soft_terms:
                query.soft_terms.append(soft)
            relaxed.append("brand")
            notices.append(f"已放宽图片识别的品牌条件（{soft}），保留为搜索关键词")
        # 3. 移除识别属性硬过滤，保留品类
        if (
            constraints.attributes.value
            and constraints.attributes.source == ConstraintSource.VISION
            and not constraints.attributes.locked_by_user
        ):
            if constraints.attributes.value:
                relaxed.append("attributes")
                notices.append("已放宽图片识别的属性条件")
        # 预算、平台、评分、用户明确品牌/型号、用户修正字段永不自动放宽（_can_relax 保证）

        query.hard_filters = hf
        return RelaxationResult(query=query, relaxed_fields=relaxed, notices=notices)
