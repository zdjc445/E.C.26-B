"""证据构建与解释事实一致性校验（§11.5、§14.7）。"""

from __future__ import annotations

from shijiajing_agent.contracts import RankedGroup, ShoppingConstraints, SkuGroup
from shijiajing_agent.domain.evidence import EvidenceBuilder, FactualConsistencyChecker


def sku_group(
    gid: str, min_price: float, max_price: float, *, platforms=("taobao",), title="索尼耳机"
) -> SkuGroup:
    from tests.unit.conftest import offer as mk_offer

    offers = [
        mk_offer(f"{gid}-{i}", platform=p, price=(min_price + max_price) / 2, title=title)
        for i, p in enumerate(platforms)
    ]
    return SkuGroup(
        group_id=gid,
        spu_id=f"spu:{gid}",
        offers=offers,
        min_price=min_price,
        max_price=max_price,
        average_price=(min_price + max_price) / 2,
        min_price_offer_id=offers[0].offer_id,
        offer_count=len(offers),
        platform_count=len(platforms),
        price_freshness=0.9,
        match_confidence=0.95,
        category_id="headphone",
        category_name="耳机",
        brand="Sony",
        model="WH-1000XM5",
        title=title,
    )


def ranked(g: SkuGroup, rank: int = 1) -> RankedGroup:
    return RankedGroup(group=g, rank=rank, ranking_score=0.9)


class TestEvidenceBuilder:
    def test_build_bundle(self):
        g = sku_group("grp1", 99.0, 129.0, platforms=("taobao", "jd"))
        bundle = EvidenceBuilder().build([ranked(g)], ShoppingConstraints())
        ev = bundle.groups[0]
        assert ev.group_id == "grp1"
        assert ev.min_price == 99.0
        assert ev.price_range == "99–129"
        assert ev.platform_names == ["taobao", "jd"]
        assert ev.offer_count == 2
        assert ev.rank == 1

    def test_missing_data_marked(self):

        g = sku_group("grp1", 99.0, 99.0)
        g.offers[0].rating = None
        g.offers[0].sales = None
        bundle = EvidenceBuilder().build([ranked(g)], ShoppingConstraints())
        assert any("评分缺失" in m for m in bundle.groups[0].missing_data)
        assert any("销量缺失" in m for m in bundle.groups[0].missing_data)

    def test_hit_conditions(self):
        c = ShoppingConstraints()
        from shijiajing_agent.contracts import SourcedValue

        c.brand = SourcedValue(value="Sony")
        g = sku_group("grp1", 99.0, 99.0)
        bundle = EvidenceBuilder().build([ranked(g)], c)
        assert any("品牌 Sony" in h for h in bundle.groups[0].hit_conditions)


class TestFactualConsistency:
    def test_allowed_numbers_pass(self):
        g = sku_group("grp1", 99.0, 129.0)
        bundle = EvidenceBuilder().build([ranked(g)], ShoppingConstraints())
        ok, violations = FactualConsistencyChecker().verify("最低 99 元，均价 114 元", bundle)
        assert ok and not violations

    def test_invented_number_fails(self):
        g = sku_group("grp1", 99.0, 129.0)
        bundle = EvidenceBuilder().build([ranked(g)], ShoppingConstraints())
        ok, violations = FactualConsistencyChecker().verify("最低 55 元", bundle)
        assert not ok
        assert any("55" in v for v in violations)

    def test_platform_not_in_evidence_fails(self):
        g = sku_group("grp1", 99.0, 99.0, platforms=("taobao",))
        bundle = EvidenceBuilder().build([ranked(g)], ShoppingConstraints())
        ok, _ = FactualConsistencyChecker().verify("在京东报价最低", bundle)
        assert not ok

    def test_template_explanation(self):
        g1 = sku_group("grp1", 99.0, 99.0, platforms=("taobao",))
        g2 = sku_group("grp2", 120.0, 120.0, platforms=("jd",))
        bundle = EvidenceBuilder().build(
            [ranked(g1, 1), ranked(g2, 2)], ShoppingConstraints(), notices=["样例数据"]
        )
        text = FactualConsistencyChecker().template_explanation(bundle)
        assert "99" in text and "120" in text
        assert "样例数据" in text

    def test_empty_bundle_template(self):
        bundle = EvidenceBuilder().build([], ShoppingConstraints())
        assert "没有符合" in FactualConsistencyChecker().template_explanation(bundle)
