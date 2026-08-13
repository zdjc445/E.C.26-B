"""Taxonomy 别名、未知值、单位换算和属性 schema（§21.1）。"""

from __future__ import annotations

import pytest

from shijiajing_agent.domain.taxonomy import Taxonomy, TaxonomyFile


class TestResolveCategory:
    def test_by_id(self, taxonomy: Taxonomy):
        assert taxonomy.resolve_category("headphone") == ("headphone", "耳机")

    def test_by_alias(self, taxonomy: Taxonomy):
        assert taxonomy.resolve_category("蓝牙耳机") == ("headphone", "耳机")

    def test_unknown(self, taxonomy: Taxonomy):
        assert taxonomy.resolve_category("不明商品") == (None, None)

    def test_blank(self, taxonomy: Taxonomy):
        assert taxonomy.resolve_category(None) == (None, None)


class TestBrandNormalization:
    def test_alias(self, taxonomy: Taxonomy):
        assert taxonomy.normalize_brand("索尼") == "Sony"

    def test_unknown_kept_verbatim(self, taxonomy: Taxonomy):
        # 显式别名之外的品牌不做猜测，原样保留（§12.3 不猜测）
        assert taxonomy.normalize_brand("NoSuchBrand") == "NoSuchBrand"

    def test_single_char_not_returned(self, taxonomy: Taxonomy):
        assert taxonomy.normalize_brand("A") is None


class TestModelNormalization:
    def test_separator_and_case(self, taxonomy: Taxonomy):
        assert taxonomy.normalize_model("wh-1000xm5", "headphone") == "WH 1000XM5"

    def test_unknown_category_keeps_text(self, taxonomy: Taxonomy):
        # 无品类规则时不转大写，但分隔符仍标准化
        assert taxonomy.normalize_model("WH-1000XM5", None) == "WH 1000XM5"

    def test_blank(self, taxonomy: Taxonomy):
        assert taxonomy.normalize_model("  ", "headphone") is None


class TestAttributeSchema:
    def test_validate_valid_enum(self, taxonomy: Taxonomy):
        assert taxonomy.validate_attribute("headphone", "noise_cancellation", "主动降噪")

    def test_validate_invalid_enum(self, taxonomy: Taxonomy):
        assert not taxonomy.validate_attribute("headphone", "noise_cancellation", "外星科技")

    def test_validate_unknown_key(self, taxonomy: Taxonomy):
        assert not taxonomy.validate_attribute("headphone", "not_a_key", "x")

    def test_validate_unknown_category(self, taxonomy: Taxonomy):
        assert not taxonomy.validate_attribute("ghost", "noise_cancellation", "x")

    def test_attribute_role(self, taxonomy: Taxonomy):
        assert taxonomy.attribute_role("headphone", "connectivity") == "identity"
        assert taxonomy.attribute_role("headphone", "color") == "variant"
        assert taxonomy.attribute_role("headphone", "noise_cancellation") == "descriptive"
        assert taxonomy.attribute_role("headphone", "bogus") is None


class TestTaxonomyFileValidation:
    def test_reject_unknown_fields(self, taxonomy_file_data: dict):
        from pydantic import ValidationError

        data = dict(taxonomy_file_data)
        data["made_up"] = 1
        with pytest.raises(ValidationError):
            Taxonomy(TaxonomyFile.model_validate(data))
