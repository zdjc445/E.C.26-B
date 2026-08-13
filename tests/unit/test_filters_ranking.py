"""硬过滤、零结果放宽（§13.5–13.6）与多阶段排序（§15）。"""

from __future__ import annotations

from shijiajing_agent.contracts import (
    ConstraintSource,
    Preference,
    RetrievalQuery,
    SellerType,
    ShoppingConstraints,
    SkuGroup,
    SortBy,
    SourcedValue,
)
from shijiajing_agent.domain.filters import HardFilterBuilder
from shijiajing_agent.domain.ranking import GroupRanker


def constraints(**overrides) -> ShoppingConstraints:
    c = ShoppingConstraints()
    for k, v in overrides.items():
        if isinstance(v, SourcedValue):
            setattr(c, k, v)
        elif k == "attributes":
            setattr(
                c,
                k,
                SourcedValue(
                    value=v, source=ConstraintSource.USER_TEXT, confidence=1.0, locked_by_user=True
                ),
            )
        else:
            setattr(c, k, SourcedValue(value=v, source=ConstraintSource.USER_TEXT))
    return c


def sv(value, source=ConstraintSource.USER_TEXT, confidence=1.0, locked=False):
    return SourcedValue(value=value, source=source, confidence=confidence, locked_by_user=locked)


class TestHardFilterBuilder:
    def test_user_values_are_hard(self):
        c = constraints(
            category_id="headphone",
            min_price=100.0,
            max_price=500.0,
            platforms=["taobao"],
            min_rating=4.0,
            brand="Sony",
            model="WH-1000XM5",
        )
        hf = HardFilterBuilder().build(c)
        assert hf.category_id == "headphone"
        assert hf.min_price == 100.0
        assert hf.max_price == 500.0
        assert hf.platforms == ["taobao"]
        assert hf.min_rating == 4.0
        assert hf.brand == "Sony"
        assert hf.model == "WH-1000XM5"

    def test_vision_brand_requires_confidence(self):
        # 品牌置信度 ≥ 0.85 才硬过滤（§13.5）
        c = constraints(brand=sv("Sony", ConstraintSource.VISION, confidence=0.9))
        assert HardFilterBuilder(brand_confidence_threshold=0.85).build(c).brand == "Sony"
        c2 = constraints(brand=sv("Sony", ConstraintSource.VISION, confidence=0.5))
        assert HardFilterBuilder(brand_confidence_threshold=0.85).build(c2).brand is None

    def test_vision_model_requires_confidence(self):
        c = constraints(model=sv("WH-1000XM5", ConstraintSource.VISION, confidence=0.95))
        assert HardFilterBuilder(model_confidence_threshold=0.90).build(c).model == "WH-1000XM5"
        c2 = constraints(model=sv("WH-1000XM5", ConstraintSource.VISION, confidence=0.8))
        assert HardFilterBuilder(model_confidence_threshold=0.90).build(c2).model is None


class TestRelaxation:
    """§13.6 只放宽图片识别产生且未被锁定的字段，顺序固定。"""

    def test_relax_vision_model_then_brand(self):
        c = constraints(
            model=sv("WH-1000XM5", ConstraintSource.VISION, confidence=0.95),
            brand=sv("Sony", ConstraintSource.VISION, confidence=0.9),
        )
        q = RetrievalQuery(
            query_text="耳机",
            hard_filters=__import__(
                "shijiajing_agent.contracts", fromlist=["HardFilters"]
            ).HardFilters(
                category_id="headphone",
                brand="Sony",
                model="WH-1000XM5",
            ),
        )
        result = HardFilterBuilder().relax(q, c)
        assert result.relaxed_fields == ["model", "brand"]
        assert result.query.hard_filters.model is None
        assert result.query.hard_filters.brand is None
        assert "WH-1000XM5" in result.query.soft_terms
        assert "Sony" in result.query.soft_terms
        assert len(result.notices) == 2

    def test_user_hard_brand_never_relaxed(self):
        c = constraints(brand=sv("Sony", ConstraintSource.USER_TEXT, locked=True))
        q = RetrievalQuery(
            hard_filters=__import__(
                "shijiajing_agent.contracts", fromlist=["HardFilters"]
            ).HardFilters(brand="Sony")
        )
        result = HardFilterBuilder().relax(q, c)
        assert result.relaxed_fields == []
        assert result.query.hard_filters.brand == "Sony"

    def test_budget_never_relaxed(self):
        c = constraints(min_price=sv(500.0, ConstraintSource.USER_TEXT, locked=True))
        q = RetrievalQuery(
            hard_filters=__import__(
                "shijiajing_agent.contracts", fromlist=["HardFilters"]
            ).HardFilters(min_price=500.0)
        )
        result = HardFilterBuilder().relax(q, c)
        assert result.query.hard_filters.min_price == 500.0


def group(
    gid: str,
    min_price: float | None,
    *,
    rating=None,
    sales=None,
    seller=SellerType.THIRD_PARTY,
    match_conf=0.9,
    brand=None,
) -> SkuGroup:
    from tests.unit.conftest import offer as mk_offer

    o = mk_offer(
        gid, price=min_price, seller_type=seller, rating=rating, sales=sales, brand=brand or "Sony"
    )
    return SkuGroup(
        group_id=gid,
        spu_id=f"spu:{gid}",
        sku_signature=None,
        offers=[o],
        min_price=min_price,
        max_price=min_price,
        average_price=min_price,
        min_price_offer_id=gid,
        offer_count=1,
        platform_count=1,
        price_freshness=0.8,
        match_confidence=match_conf,
        category_id="headphone",
        category_name="耳机",
        brand=o.brand,
        model=o.model,
        title=o.title,
    )


class TestSorting:
    def test_price_asc_with_tiebreak(self):
        ranker = GroupRanker()
        g1 = group("g1", 200.0, match_conf=0.8)
        g2 = group("g2", 100.0, match_conf=0.9)
        g3 = group("g3", 100.0, match_conf=0.7)
        r = ranker.rank([g1, g2, g3], constraints(), sort_by=SortBy.PRICE_ASC)
        assert [rg.group.group_id for rg in r.ranked] == ["g2", "g3", "g1"]

    def test_price_desc(self):
        r = GroupRanker().rank(
            [group("g1", 100.0), group("g2", 300.0)], constraints(), sort_by=SortBy.PRICE_DESC
        )
        assert [rg.group.group_id for rg in r.ranked] == ["g2", "g1"]

    def test_rating_desc_missing_last(self):
        r = GroupRanker().rank(
            [
                group("g1", 100.0, rating=None),
                group("g2", 300.0, rating=4.8),
                group("g3", 200.0, rating=4.5),
            ],
            constraints(),
            sort_by=SortBy.RATING_DESC,
        )
        assert [rg.group.group_id for rg in r.ranked] == ["g2", "g3", "g1"]

    def test_sales_desc_missing_last(self):
        r = GroupRanker().rank(
            [group("g1", 100.0, sales=None), group("g2", 300.0, sales=999.0)],
            constraints(),
            sort_by=SortBy.SALES_DESC,
        )
        assert [rg.group.group_id for rg in r.ranked] == ["g2", "g1"]

    def test_recommended_score_desc(self):
        r = GroupRanker().rank(
            [group("g1", 100.0), group("g2", 300.0)], constraints(), sort_by=SortBy.RECOMMENDED
        )
        scores = [rg.ranking_score for rg in r.ranked]
        assert scores == sorted(scores, reverse=True)
        assert [rg.rank for rg in r.ranked] == [1, 2]

    def test_stable_tiebreak_by_group_id(self):
        r1 = GroupRanker().rank(
            [group("g1", 100.0, match_conf=0.9), group("g2", 100.0, match_conf=0.9)],
            constraints(),
            sort_by=SortBy.PRICE_ASC,
        )
        assert [rg.group.group_id for rg in r1.ranked] == ["g1", "g2"]

    def test_missing_dimensions_renormalized_not_punished(self):
        ranker = GroupRanker()
        g_no_rating = group("g1", 100.0, rating=None, sales=None)
        r = ranker.rank([g_no_rating], constraints(), sort_by=SortBy.RECOMMENDED)
        assert "rating_quality" in r.ranked[0].missing_dimensions
        # 分数基于剩余维度计算，不为缺失维度记 0 分
        assert r.ranked[0].ranking_score > 0


class TestPreferences:
    def test_lowest_price_raises_price_weight(self):
        base = GroupRanker()._effective_weights([])
        pref = GroupRanker()._effective_weights([Preference.LOWEST_PRICE])
        assert pref["price_utility"] > base["price_utility"]

    def test_fast_delivery_no_field_no_score(self):
        ranker = GroupRanker()
        r = ranker.rank([group("g1", 100.0)], constraints(), preferences=[Preference.FAST_DELIVERY])
        assert "freshness" in r.ranked[0].missing_dimensions

    def test_high_sales_adds_sales_dimension(self):
        ranker = GroupRanker()
        g = group("g1", 100.0, sales=500.0)
        base = ranker.rank([g], constraints(), preferences=[], sort_by=SortBy.RECOMMENDED)
        pref = ranker.rank(
            [g], constraints(), preferences=[Preference.HIGH_SALES], sort_by=SortBy.RECOMMENDED
        )
        assert pref.ranked[0].sales_quality == base.ranked[0].sales_quality
        assert "sales_quality" in pref.weights_used

    def test_official_store_preference_boosts_trust(self):
        ranker = GroupRanker()
        g_third = group("g1", 100.0, seller=SellerType.THIRD_PARTY)
        g_official = group("g2", 200.0, seller=SellerType.OFFICIAL)
        r = ranker.rank(
            [g_third, g_official], constraints(), preferences=[Preference.OFFICIAL_STORE]
        )
        # 官方店信任分更高
        by_id = {rg.group.group_id: rg.seller_trust for rg in r.ranked}
        assert by_id["g2"] > by_id["g1"]
