"""多阶段确定性排序（方案 §15）。

原则：
- 硬过滤先于排序。
- 同款置信度优先于低价诱惑。
- 用户显式排序优先于推荐分。
- LLM 不参与数值排序。

所有分量归一化到 [0,1]；缺失维度从分母移除并对剩余权重重新归一化。
最终稳定 tie-breaker 为 group_id 升序，保证回归测试可重复。
"""

from __future__ import annotations

from dataclasses import dataclass

from shijiajing_agent.contracts import (
    Preference,
    RankedGroup,
    SellerType,
    ShoppingConstraints,
    SkuGroup,
    SortBy,
)

_BASE_WEIGHTS: dict[str, float] = {
    "intent_relevance": 0.30,
    "match_confidence": 0.25,
    "price_utility": 0.20,
    "seller_trust": 0.10,
    "rating_quality": 0.10,
    "freshness": 0.05,
}

# 偏好权重表（§15.4，配置化、版本化并进入 trace）
_DEFAULT_PREFERENCE_WEIGHTS: dict[str, dict[str, float]] = {
    Preference.LOWEST_PRICE.value: {"price_utility": 0.35, "intent_relevance": 0.25},
    Preference.OFFICIAL_STORE.value: {"seller_trust": 0.25, "intent_relevance": 0.25},
    Preference.HIGH_RATING.value: {"rating_quality": 0.25, "intent_relevance": 0.25},
    Preference.HIGH_SALES.value: {"sales_quality": 0.20},
    Preference.FAST_DELIVERY.value: {"freshness": 0.25, "intent_relevance": 0.25},
}


@dataclass(frozen=True)
class RankResult:
    ranked: list[RankedGroup]
    weights_used: dict[str, float]
    weight_version: str = "2026.08.1"


class GroupRanker:
    """确定性排序器。纯同步函数，结果可复现。"""

    def __init__(self, preference_weights: dict[str, dict[str, float]] | None = None) -> None:
        self._pref_weights = preference_weights or _DEFAULT_PREFERENCE_WEIGHTS

    def rank(
        self,
        groups: list[SkuGroup],
        constraints: ShoppingConstraints,
        *,
        sort_by: SortBy = SortBy.RECOMMENDED,
        preferences: list[Preference] | None = None,
    ) -> RankResult:
        prefs = [p for p in (preferences or []) if p in list(Preference)]
        weights = self._effective_weights(prefs)

        ranked: list[RankedGroup] = []
        global_min = min((g.min_price for g in groups if g.min_price is not None), default=None)
        global_max = max((g.max_price for g in groups if g.max_price is not None), default=None)
        max_rating = max(
            (g.offers[0].rating for g in groups if g.offers and g.offers[0].rating is not None),
            default=None,
        )
        max_sales = max(
            (g.offers[0].sales for g in groups if g.offers and g.offers[0].sales is not None),
            default=None,
        )

        for _, g in enumerate(groups):
            dims, missing = self._score_dimensions(
                g, constraints, global_min, global_max, max_rating, max_sales, prefs
            )
            active = {k: w for k, w in weights.items() if k not in missing}
            total = sum(active.values())
            score = sum(active[k] * dims.get(k, 0.0) for k in active) / total if total else 0.0
            ranked.append(
                RankedGroup(
                    group=g,
                    rank=0,
                    ranking_score=round(score, 6),
                    intent_relevance=round(dims.get("intent_relevance", 0.0), 4),
                    match_confidence=g.match_confidence,
                    price_utility=round(dims.get("price_utility", 0.0), 4),
                    seller_trust=round(dims.get("seller_trust", 0.0), 4),
                    rating_quality=round(dims.get("rating_quality", 0.0), 4),
                    sales_quality=round(dims.get("sales_quality", 0.0), 4),
                    freshness=round(dims.get("freshness", 0.0), 4),
                    missing_dimensions=sorted(missing),
                )
            )

        ranked = self._sort(ranked, sort_by)
        for i, r in enumerate(ranked):
            r.rank = i + 1
        return RankResult(ranked=ranked, weights_used=weights)

    # ------------------------------------------------------------------
    def _effective_weights(self, prefs: list[Preference]) -> dict[str, float]:
        """偏好作用权重表：从 base 权重叠加偏好增量后重新归一化（§15.4）。"""
        w = dict(_BASE_WEIGHTS)
        for p in prefs:
            delta = self._pref_weights.get(p.value)
            if not delta:
                continue
            for dim, target in delta.items():
                base = _BASE_WEIGHTS.get(dim, 0.0)
                if base > 0:
                    w[dim] = max(target, base)  # 只提升，不降低
                elif dim == "sales_quality":
                    w[dim] = target  # 新维度
        # 归一化到 1
        total = sum(w.values())
        if total > 0:
            w = {k: v / total for k, v in w.items()}
        return w

    def _score_dimensions(
        self,
        g: SkuGroup,
        constraints: ShoppingConstraints,
        global_min: float | None,
        global_max: float | None,
        max_rating: float | None,
        max_sales: float | None,
        prefs: list[Preference],
    ) -> tuple[dict[str, float], set[str]]:
        dims: dict[str, float] = {}
        missing: set[str] = set()

        dims["match_confidence"] = g.match_confidence
        dims["intent_relevance"] = self._intent_relevance(g, constraints)
        dims["price_utility"] = self._price_utility(g, global_min, global_max)
        dims["seller_trust"] = self._seller_trust(g, prefs)
        if g.offers and g.offers[0].rating is not None and max_rating:
            dims["rating_quality"] = max(0.0, min(1.0, g.offers[0].rating / max_rating))
        else:
            missing.add("rating_quality")
        if g.offers and g.offers[0].sales is not None and max_sales:
            import math

            dims["sales_quality"] = max(
                0.0, min(1.0, math.log1p(g.offers[0].sales) / math.log1p(max_sales))
            )
        else:
            missing.add("sales_quality")
        if g.price_freshness is not None:
            dims["freshness"] = g.price_freshness
        else:
            missing.add("freshness")

        # fast_delivery：只有真实配送字段存在时才评分（§15.4）
        if Preference.FAST_DELIVERY in prefs and (
            not g.offers or g.offers[0].delivery_days is None
        ):
            missing.add("freshness")

        return dims, missing

    def _intent_relevance(self, g: SkuGroup, constraints: ShoppingConstraints) -> float:
        """命中用户约束的比例；无属性约束时取中性 0.5。"""
        hits: list[float] = []
        if constraints.brand.value:
            hits.append(1.0 if constraints.brand.value == g.brand else 0.0)
        if constraints.model.value:
            hits.append(1.0 if constraints.model.value == g.model else 0.0)
        colors = constraints.colors.value
        if colors:
            sku_colors = {str(v).lower() for v in g.sku_attributes.get("color", "").split(",")}
            hits.append(
                sum(
                    1
                    for c in colors
                    if str(c).lower() in sku_colors
                    or str(c).lower() == str(g.sku_attributes.get("color", "")).lower()
                )
                / len(colors)
            )
        user_attrs = constraints.attributes.value
        if user_attrs:
            matched = sum(
                1
                for k, v in user_attrs.items()
                if str(g.sku_attributes.get(k, "")) == str(v)
                or any(str(o.variant_attributes.get(k, "")) == str(v) for o in g.offers)
            )
            hits.append(matched / len(user_attrs))
        if not hits:
            return 0.5
        return sum(hits) / len(hits)

    @staticmethod
    def _price_utility(g: SkuGroup, global_min: float | None, global_max: float | None) -> float:
        if g.min_price is None:
            return 0.0
        if global_min is None or global_max is None or global_max == global_min:
            return 1.0 if g.min_price == global_min else 0.5
        return max(0.0, 1.0 - (g.min_price - global_min) / (global_max - global_min))

    @staticmethod
    def _seller_trust(g: SkuGroup, prefs: list[Preference]) -> float:
        if not g.offers:
            return 0.0
        sellers = [o.seller_type for o in g.offers]
        trust = {
            SellerType.OFFICIAL: 1.0,
            SellerType.SELF_OPERATED: 0.85,
            SellerType.THIRD_PARTY: 0.5,
            SellerType.UNKNOWN: 0.3,
        }
        base = max(trust.get(s, 0.3) for s in sellers)
        if Preference.OFFICIAL_STORE in prefs:
            # 官方/自营加分，第三方相对降权（§15.4）
            if any(s in (SellerType.OFFICIAL, SellerType.SELF_OPERATED) for s in sellers):
                base = min(1.0, base + 0.15)
            else:
                base = max(0.0, base - 0.15)
        return base

    # ------------------------------------------------------------------
    def _sort(self, ranked: list[RankedGroup], sort_by: SortBy) -> list[RankedGroup]:
        def rating(g: RankedGroup) -> tuple[float, int]:
            r = (
                g.group.offers[0].rating
                if g.group.offers and g.group.offers[0].rating is not None
                else -1.0
            )
            return (r, 0 if r >= 0 else 1)

        def sales(g: RankedGroup) -> tuple[float, int]:
            s = (
                g.group.offers[0].sales
                if g.group.offers and g.group.offers[0].sales is not None
                else -1.0
            )
            return (s, 0 if s >= 0 else 1)

        def min_price(g: RankedGroup) -> float:
            return g.group.min_price if g.group.min_price is not None else float("inf")

        def conf(g: RankedGroup) -> float:
            return g.group.match_confidence

        def gid(g: RankedGroup) -> str:
            return g.group.group_id

        if sort_by == SortBy.PRICE_ASC:
            ranked.sort(key=lambda g: (min_price(g), -conf(g), gid(g)))
        elif sort_by == SortBy.PRICE_DESC:
            ranked.sort(key=lambda g: (-min_price(g), -conf(g), gid(g)))
        elif sort_by == SortBy.RATING_DESC:
            ranked.sort(key=lambda g: (rating(g)[1], -rating(g)[0], gid(g)))
        elif sort_by == SortBy.SALES_DESC:
            ranked.sort(key=lambda g: (sales(g)[1], -sales(g)[0], gid(g)))
        else:  # recommended
            ranked.sort(key=lambda g: (-g.ranking_score, -conf(g), gid(g)))
        return ranked
