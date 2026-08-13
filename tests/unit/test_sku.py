"""SKU 拆分、价格去重与聚合（§14.6–14.7）。"""

from __future__ import annotations

import pytest

from shijiajing_agent.domain.normalization import TaxonomyNormalizer
from shijiajing_agent.domain.sku import SkuSplitter
from tests.unit.conftest import offer


def norm(taxonomy, o):
    return TaxonomyNormalizer(taxonomy).normalize_offer(o)


@pytest.fixture
def splitter(taxonomy):
    return SkuSplitter(taxonomy)


class TestSkuSplit:
    def test_variant_attributes_split_groups(self, taxonomy, splitter):
        members = [
            norm(taxonomy, offer("a1", variant={"color": "黑色", "set_type": "单件"})),
            norm(taxonomy, offer("b1", variant={"color": "黑色", "set_type": "单件"})),
            norm(taxonomy, offer("c1", variant={"color": "白色", "set_type": "单件"})),
        ]
        groups = splitter.split_spu(members, "spu:test")
        assert len(groups) == 2
        by_signature = {g.sku_signature: g for g in groups}
        black = by_signature.get("color=黑色|set_type=单件")
        white = by_signature.get("color=白色|set_type=单件")
        assert black is not None and white is not None
        assert black.offer_count == 2
        assert white.offer_count == 1

    def test_missing_sku_attribute_becomes_single_group(self, taxonomy, splitter):
        members = [
            norm(taxonomy, offer("a1", variant={"color": "黑色", "set_type": "单件"})),
            norm(taxonomy, offer("b1", variant={"color": "黑色"})),  # 缺少 set_type
        ]
        groups = splitter.split_spu(members, "spu:test")
        assert len(groups) == 2
        single = [g for g in groups if g.missing_sku_attributes]
        assert len(single) == 1
        assert single[0].offer_count == 1
        assert "关键销售属性缺失" in single[0].risks[0]
        # 缺失关键属性降 confidence（×0.9）
        assert single[0].match_confidence < 1.0

    def test_no_variant_keys_single_group(self, taxonomy, splitter):
        members = [
            norm(taxonomy, offer("a1", variant={})),
            norm(taxonomy, offer("b1", variant={})),
        ]
        groups = splitter.split_spu(members, "spu:test")
        assert len(groups) == 1
        assert groups[0].offer_count == 2


class TestPriceAggregation:
    def test_payable_price_formula(self, taxonomy, splitter):
        """§14.7 payable_price = price - coupon + shipping。"""
        members = [
            norm(taxonomy, offer("a1", price=100.0, coupon=10.0, shipping=5.0)),
            norm(taxonomy, offer("b1", price=120.0)),
        ]
        groups = splitter.split_spu(members, "spu:test")
        g = groups[0]
        assert g.min_price == pytest.approx(95.0)  # a1: 100-10+5
        assert g.max_price == pytest.approx(120.0)
        assert g.average_price == pytest.approx((95.0 + 120.0) / 2)
        assert g.min_price_offer_id == "a1"

    def test_dedup_by_platform_shop_product_keeps_newest(self, taxonomy, splitter):
        members = [
            norm(
                taxonomy,
                offer(
                    "a1",
                    platform="taobao",
                    source_product_id="sp-1",
                    source_updated_at="2026-08-01T00:00:00Z",
                    price=100.0,
                ),
            ),
            norm(
                taxonomy,
                offer(
                    "a2",
                    platform="taobao",
                    source_product_id="sp-1",
                    source_updated_at="2026-08-10T00:00:00Z",
                    price=90.0,
                ),
            ),
        ]
        groups = splitter.split_spu(members, "spu:test")
        assert groups[0].offer_count == 1
        assert groups[0].offers[0].offer_id == "a2"

    def test_different_platforms_not_deduped(self, taxonomy, splitter):
        members = [
            norm(taxonomy, offer("a1", platform="taobao")),
            norm(taxonomy, offer("b1", platform="jd")),
        ]
        groups = splitter.split_spu(members, "spu:test")
        assert groups[0].offer_count == 2
        assert groups[0].platform_count == 2

    def test_no_price_offers_aggregate_to_none(self, taxonomy, splitter):
        members = [norm(taxonomy, offer("a1", price=None))]
        groups = splitter.split_spu(members, "spu:test")
        assert groups[0].min_price is None
        assert groups[0].offer_count == 1


class TestGroupId:
    def test_group_id_stable(self, taxonomy, splitter):
        members = [norm(taxonomy, offer("a1")), norm(taxonomy, offer("b1"))]
        g1 = splitter.split_spu(members, "spu:test")[0]
        g2 = splitter.split_spu(members, "spu:test")[0]
        assert g1.group_id == g2.group_id
        assert g1.group_id.startswith("spu:test:")
