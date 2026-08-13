"""Offer 字段标准化与单位换算（§12.3）。"""

from __future__ import annotations

from shijiajing_agent.contracts import Offer
from shijiajing_agent.domain.normalization import TaxonomyNormalizer
from tests.unit.conftest import offer


def make(taxonomy, o: Offer):
    return TaxonomyNormalizer(taxonomy).normalize_offer(o)


class TestOfferNormalization:
    def test_basic_fields(self, taxonomy):
        n = make(taxonomy, offer("a1"))
        assert n.normalized_category_id == "headphone"
        assert n.normalized_brand == "Sony"
        assert n.normalized_model == "WH 1000XM5"
        assert n.normalization_failures == []

    def test_alias_brand_normalized(self, taxonomy):
        n = make(taxonomy, offer("a1", brand="索尼"))
        assert n.normalized_brand == "Sony"

    def test_unknown_category_kept_null(self, taxonomy):
        n = make(taxonomy, offer("a1", category_id="ghost"))
        assert n.normalized_category_id is None

    def test_attribute_enum_canonicalized(self, taxonomy):
        n = make(
            taxonomy, offer("a1", identity={"connectivity": "蓝牙", "wearing_style": "头戴式"})
        )
        assert n.normalized_identity == {"connectivity": "蓝牙", "wearing_style": "头戴式"}

    def test_attribute_normalization_failure_flagged(self, taxonomy):
        n = make(taxonomy, offer("a1", identity={"wearing_style": "不存在的样式"}))
        # 未标准化属性不参与硬匹配，并记录失败
        assert "identity:wearing_style" in n.normalization_failures


class TestUnitConversion:
    def test_liters(self, taxonomy):
        n = make(
            taxonomy,
            offer(
                "a1",
                category_id="backpack",
                identity={"capacity_liters": "20升", "material": "尼龙"},
            ),
        )
        assert n.normalized_identity["capacity_liters"] == "20L"

    def test_ml_to_liters(self, taxonomy):
        n = make(
            taxonomy,
            offer(
                "a1",
                category_id="backpack",
                identity={"capacity_liters": "500毫升", "material": "尼龙"},
            ),
        )
        assert n.normalized_identity["capacity_liters"] == "0.5L"

    def test_watts(self, taxonomy):
        n = make(
            taxonomy,
            offer(
                "a1", category_id="hair_dryer", identity={"power": "1600瓦", "ion_type": "负离子"}
            ),
        )
        assert n.normalized_identity["power"] == "1600W"

    def test_kw_to_watts(self, taxonomy):
        n = make(
            taxonomy,
            offer(
                "a1", category_id="hair_dryer", identity={"power": "1.6kW", "ion_type": "负离子"}
            ),
        )
        assert n.normalized_identity["power"] == "1600W"


class TestRecognitionNormalization:
    def test_resolve(self, taxonomy):
        norm = TaxonomyNormalizer(taxonomy).normalize_recognition(
            category_id="耳机",
            brand="索尼",
            model="wh-1000xm5",
            attributes={"noise_cancellation": "主动降噪"},
        )
        assert norm["category_id"] == "headphone"
        assert norm["brand"] == "Sony"
        assert norm["model"] == "WH 1000XM5"

    def test_unknown_values_nulled(self, taxonomy):
        norm = TaxonomyNormalizer(taxonomy).normalize_recognition(
            category_id="ghost",
            brand="A",
            model=None,
            attributes={},
        )
        assert norm["category_id"] is None
        assert norm["brand"] is None


class TestTitleSimilarity:
    def test_similar_titles(self):
        sim = TaxonomyNormalizer.title_token_similarity(
            "Sony 索尼 WH-1000XM5 头戴式无线降噪耳机",
            "Sony 索尼 WH-1000XM5 无线降噪耳机 头戴式",
        )
        assert sim > 0.5

    def test_disjoint_titles(self):
        sim = TaxonomyNormalizer.title_token_similarity("苹果手机", "运动鞋跑步")
        assert sim == 0.0

    def test_model_equivalent(self):
        assert TaxonomyNormalizer.model_equivalent("WH-1000XM5", "WH 1000XM5")
        assert TaxonomyNormalizer.model_equivalent("wh_1000xm5", "WH-1000XM5")
        assert not TaxonomyNormalizer.model_equivalent("WH-1000XM5", "WH-1000XM4")
