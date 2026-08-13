"""约束合并、冲突检测与澄清构建（§8、§7.4、§16）。"""

from __future__ import annotations

import pytest

from shijiajing_agent.contracts import (
    ConstraintSource,
    IntentPatch,
    Preference,
    RecognitionCorrection,
    RecognitionResult,
    ShoppingConstraints,
    SortBy,
    SourcedValue,
)
from shijiajing_agent.domain.constraints import (
    ClarificationBuilder,
    ConstraintConflictError_,
    ConstraintMerger,
)


def _vision(**overrides) -> RecognitionResult:
    base = dict(
        recognition_id="rec-1",
        category_id="headphone",
        category_name="耳机",
        brand="Sony",
        model="WH-1000XM5",
        field_confidences={"category_id": 0.95, "brand": 0.9, "model": 0.9},
        overall_confidence=0.9,
    )
    base.update(overrides)
    return RecognitionResult(**base)


@pytest.fixture
def merger(taxonomy):
    return ConstraintMerger(taxonomy)


class TestPriorityOrder:
    """§8.1 单字段覆盖顺序：修正 > 当前文本 > 历史 locked > 图片 > 历史文本 > 历史图片 > 默认。"""

    def test_user_correction_beats_text(self, merger):
        result = merger.merge(
            prev=None,
            vision=None,
            intent=IntentPatch(brand="Sony"),
            correction=RecognitionCorrection(recognition_id="rec-1", brand="Bose"),
            new_subject=True,
            turn_id="t1",
        )
        assert result.constraints.brand.value == "Bose"
        assert result.constraints.brand.source == ConstraintSource.USER_CORRECTION
        assert result.constraints.brand.locked_by_user

    def test_vision_loses_to_user_text(self, merger):
        result = merger.merge(
            prev=None,
            vision=_vision(brand="Bose"),
            intent=IntentPatch(brand="Sony"),
            correction=None,
            new_subject=True,
            turn_id="t1",
        )
        assert result.constraints.brand.value == "Sony"
        assert result.constraints.brand.source == ConstraintSource.USER_TEXT

    def test_vision_applies_when_no_text(self, merger):
        result = merger.merge(
            prev=None,
            vision=_vision(),
            intent=None,
            correction=None,
            new_subject=True,
            turn_id="t1",
        )
        assert result.constraints.brand.value == "Sony"
        assert result.constraints.brand.source == ConstraintSource.VISION
        assert result.constraints.category_id.value == "headphone"

    def test_user_text_survives_next_vision_turn(self, merger):
        r1 = merger.merge(
            prev=None,
            vision=None,
            intent=IntentPatch(brand="Sony"),
            correction=None,
            new_subject=True,
            turn_id="t1",
        )
        r2 = merger.merge(
            prev=r1.constraints,
            vision=_vision(brand="Bose"),
            intent=None,
            correction=None,
            new_subject=False,
            turn_id="t2",
        )
        # 历史 locked 用户文本优先于当前图片识别
        assert r2.constraints.brand.value == "Sony"
        assert r2.constraints.brand.source == ConstraintSource.USER_TEXT


class TestListRules:
    """§8.2 列表字段规则。"""

    def test_colors_replaced_on_new_mention(self, merger):
        r1 = merger.merge(
            prev=None,
            vision=None,
            intent=IntentPatch(colors=["黑"]),
            correction=None,
            new_subject=True,
            turn_id="t1",
        )
        r2 = merger.merge(
            prev=r1.constraints,
            vision=None,
            intent=IntentPatch(colors=["白"]),
            correction=None,
            new_subject=False,
            turn_id="t2",
        )
        assert r2.constraints.colors.value == ["白"]

    def test_preferences_accumulate(self, merger):
        r1 = merger.merge(
            prev=None,
            vision=None,
            intent=IntentPatch(preferences=[Preference.LOWEST_PRICE]),
            correction=None,
            new_subject=True,
            turn_id="t1",
        )
        r2 = merger.merge(
            prev=r1.constraints,
            vision=None,
            intent=IntentPatch(preferences=[Preference.HIGH_RATING]),
            correction=None,
            new_subject=False,
            turn_id="t2",
        )
        assert set(r2.constraints.preferences.value) == {
            Preference.LOWEST_PRICE,
            Preference.HIGH_RATING,
        }

    def test_cancelled_preference_removed(self, merger):
        r1 = merger.merge(
            prev=None,
            vision=None,
            intent=IntentPatch(preferences=[Preference.LOWEST_PRICE, Preference.HIGH_RATING]),
            correction=None,
            new_subject=True,
            turn_id="t1",
        )
        r2 = merger.merge(
            prev=r1.constraints,
            vision=None,
            intent=IntentPatch(cancelled_preferences=[Preference.LOWEST_PRICE]),
            correction=None,
            new_subject=False,
            turn_id="t2",
        )
        assert r2.constraints.preferences.value == [Preference.HIGH_RATING]

    def test_attributes_merged_by_key(self, merger):
        r1 = merger.merge(
            prev=None,
            vision=None,
            intent=IntentPatch(attributes={"color": "黑"}),
            correction=None,
            new_subject=True,
            turn_id="t1",
        )
        r2 = merger.merge(
            prev=r1.constraints,
            vision=None,
            intent=IntentPatch(attributes={"set_type": "套装"}),
            correction=None,
            new_subject=False,
            turn_id="t2",
        )
        assert r2.constraints.attributes.value == {"color": "黑", "set_type": "套装"}


class TestClearFields:
    def test_clear_prevents_low_priority_refill(self, merger):
        r1 = merger.merge(
            prev=None,
            vision=_vision(brand="Bose"),
            intent=IntentPatch(brand="Sony"),
            correction=None,
            new_subject=True,
            turn_id="t1",
        )
        r2 = merger.merge(
            prev=r1.constraints,
            vision=_vision(brand="Bose"),
            intent=IntentPatch(clear_fields=["brand"]),
            correction=None,
            new_subject=False,
            turn_id="t2",
        )
        assert r2.constraints.brand.value is None
        # 图片识别不得补回被 clear 的品牌
        assert r2.constraints.brand.source == ConstraintSource.DEFAULT
        assert "brand" in r2.constraints.clear_fields

    def test_clear_field_stays_cleared_next_turn(self, merger):
        r1 = merger.merge(
            prev=None,
            vision=None,
            intent=IntentPatch(clear_fields=["model"]),
            correction=None,
            new_subject=True,
            turn_id="t1",
        )
        r2 = merger.merge(
            prev=r1.constraints,
            vision=_vision(),
            intent=None,
            correction=None,
            new_subject=False,
            turn_id="t2",
        )
        assert r2.constraints.model.value is None


class TestNewSubject:
    """§7.4 新图片创建新 subject_id，只保留通用偏好。"""

    def test_product_fields_cleared(self, merger):
        r1 = merger.merge(
            prev=None,
            vision=_vision(brand="Sony", model="WH-1000XM5"),
            intent=None,
            correction=None,
            new_subject=True,
            turn_id="t1",
        )
        r2 = merger.merge(
            prev=r1.constraints,
            vision=_vision(brand="Bose", model="QC45", category_id="headphone"),
            intent=None,
            correction=None,
            new_subject=True,
            turn_id="t2",
        )
        # 新 subject：brand/model 来自新图片而非旧商品
        assert r2.constraints.brand.value == "Bose"
        assert r2.constraints.model.value == "QC45"

    def test_general_preferences_preserved(self, merger):
        r1 = merger.merge(
            prev=None,
            vision=None,
            intent=IntentPatch(
                min_price=100,
                max_price=500,
                platforms=["taobao"],
                min_rating=4.0,
                sort_by=SortBy.PRICE_ASC,
            ),
            correction=None,
            new_subject=True,
            turn_id="t1",
        )
        r2 = merger.merge(
            prev=r1.constraints,
            vision=_vision(),
            intent=None,
            correction=None,
            new_subject=True,
            turn_id="t2",
        )
        assert r2.constraints.min_price.value == 100
        assert r2.constraints.platforms.value == ["taobao"]
        assert r2.constraints.min_rating.value == 4.0
        assert r2.constraints.sort_by.value == SortBy.PRICE_ASC
        # 商品字段来自新图片识别（§7.4），颜色未识别则保持空
        assert r2.constraints.category_id.value == "headphone"
        assert r2.constraints.colors.value is None


class TestConflicts:
    """§8.3 冲突进入 clarification。"""

    def test_text_vs_high_conf_vision_category(self, merger):
        result = merger.merge(
            prev=None,
            vision=_vision(category_id="headphone", category_name="耳机"),
            intent=IntentPatch(category_id="sneaker"),
            correction=None,
            new_subject=True,
            turn_id="t1",
        )
        assert any(c.reason_code == "CATEGORY_CONFLICT" for c in result.conflicts)

    def test_low_conf_vision_category_yields_notice_not_conflict(self, merger):
        result = merger.merge(
            prev=None,
            vision=_vision(
                category_id="headphone",
                field_confidences={"category_id": 0.4},
                overall_confidence=0.4,
            ),
            intent=IntentPatch(category_id="sneaker"),
            correction=None,
            new_subject=True,
            turn_id="t1",
        )
        assert not result.conflicts
        assert any("置信度较低" in n for n in result.notices)

    def test_correction_vs_text_brand(self, merger):
        result = merger.merge(
            prev=None,
            vision=None,
            intent=IntentPatch(brand="Sony"),
            correction=RecognitionCorrection(recognition_id="rec-1", brand="Bose"),
            new_subject=True,
            turn_id="t1",
        )
        assert any(c.reason_code == "BRAND_CONFLICT" for c in result.conflicts)

    def test_price_range_conflict(self, merger):
        result = merger.merge(
            prev=None,
            vision=None,
            intent=IntentPatch(min_price=500, max_price=100),
            correction=None,
            new_subject=True,
            turn_id="t1",
        )
        assert any(c.reason_code == "PRICE_RANGE_CONFLICT" for c in result.conflicts)

    def test_unknown_attribute_conflict(self, merger):
        result = merger.merge(
            prev=None,
            vision=None,
            intent=IntentPatch(category_id="headphone", attributes={"not_a_key": "x"}),
            correction=None,
            new_subject=True,
            turn_id="t1",
        )
        assert any(c.reason_code == "UNKNOWN_ATTRIBUTE" for c in result.conflicts)

    def test_unknown_category_raises(self, merger):
        with pytest.raises(ConstraintConflictError_):
            merger.merge(
                prev=None,
                vision=None,
                intent=IntentPatch(category_id="ghost"),
                correction=None,
                new_subject=True,
                turn_id="t1",
            )


class TestClarificationBuilder:
    def test_missing_category_options_from_taxonomy(self, taxonomy):
        c = ClarificationBuilder().build(
            question_id="q1",
            subject_id="sub-1",
            turn_id="t1",
            reason_code="MISSING_CATEGORY",
            taxonomy=taxonomy,
        )
        assert c.reason_code == "MISSING_CATEGORY"
        assert c.missing_fields == ["category_id"]
        assert len(c.options) >= 5
        assert any(o.option_id == "cat:headphone" for o in c.options)

    def test_conflict_options(self):
        from shijiajing_agent.domain.constraints import ConstraintConflict

        conflict = ConstraintConflict(
            reason_code="BRAND_CONFLICT",
            field="brand",
            message="冲突",
            a_value="Sony",
            b_value="Bose",
        )
        c = ClarificationBuilder().build(
            question_id="q2",
            subject_id="sub-1",
            turn_id="t1",
            reason_code="CONFLICT",
            conflict=conflict,
        )
        assert len(c.options) == 2
        assert c.options[0].option_id == "conf:BRAND_CONFLICT:a"

    def test_identity_missing(self):
        c = ClarificationBuilder().build(
            question_id="q3",
            subject_id="sub-1",
            turn_id="t1",
            reason_code="IDENTITY_MISSING",
            missing_fields=["connectivity"],
        )
        assert c.missing_fields == ["connectivity"]


class TestSourcedValueDefaults:
    def test_default_sourced_value(self):
        sv = SourcedValue()
        assert sv.value is None
        assert sv.source == ConstraintSource.DEFAULT
        assert sv.confidence == 0.0
        assert not sv.locked_by_user

    def test_shopping_constraints_defaults(self):
        c = ShoppingConstraints()
        assert c.effective_value("category_id") is None
        assert not c.is_user_locked("brand")
