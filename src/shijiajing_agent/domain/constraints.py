"""约束合并、冲突检测与澄清构建（方案 §7.1、§7.4、§8、§16）。

合并顺序与列表规则严格按方案 §8 实现；全部为同步纯函数。
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field as dc_field
from typing import Any

from shijiajing_agent.contracts import (
    Clarification,
    ClarificationOption,
    ConstraintSource,
    IntentPatch,
    Preference,
    RecognitionCorrection,
    RecognitionResult,
    ShoppingConstraints,
    SourcedValue,
)
from shijiajing_agent.domain.taxonomy import Taxonomy

# 图片品类视为"高置信"参与冲突的置信度阈值
CATEGORY_CONFLICT_CONFIDENCE_THRESHOLD = 0.70

# 优先级高于当前图片识别（§8.1 第 1–3 位）的来源：用户修正、用户文本、用户选项。
# 这些来源已确定的值不允许被当前图片识别覆盖。
_HIGHER_THAN_VISION = (
    ConstraintSource.USER_CORRECTION,
    ConstraintSource.USER_TEXT,
    ConstraintSource.SELECTED_OPTION,
)

# 新图片时保留的跨商品通用偏好（§7.4）
_PRESERVED_ON_NEW_SUBJECT = (
    "min_price",
    "max_price",
    "platforms",
    "min_rating",
    "sort_by",
    "preferences",
)
# 新图片时清除的商品相关字段
_CLEARED_ON_NEW_SUBJECT = (
    "category_id",
    "category_name",
    "brand",
    "model",
    "colors",
    "attributes",
)


class ConstraintConflictError_(ValueError):
    """合并过程中的冲突（供节点捕获并转为澄清）。"""


@dataclass
class ConstraintConflict:
    reason_code: str
    field: str
    message: str
    a_value: Any = None
    b_value: Any = None


@dataclass
class MergeResult:
    constraints: ShoppingConstraints
    conflicts: list[ConstraintConflict] = dc_field(default_factory=list[ConstraintConflict])
    notices: list[str] = dc_field(default_factory=list[str])


def _sv(
    value: Any,
    source: ConstraintSource,
    turn_id: str | None,
    *,
    locked: bool = False,
    confidence: float = 1.0,
) -> SourcedValue:
    return SourcedValue(
        value=value,
        source=source,
        confidence=confidence,
        updated_turn_id=turn_id,
        locked_by_user=locked,
    )


class ConstraintMerger:
    """按 §8.1 优先级合并多来源约束。

    单字段覆盖顺序（同一 subject_id）：
    1. 当前轮用户修正        2. 当前轮用户文本明确修改
    3. 历史轮次 locked 值     4. 当前轮图片识别结果
    5. 历史轮次用户文本值     6. 历史图片识别值
    7. 系统默认值
    """

    def __init__(self, taxonomy: Taxonomy) -> None:
        self._taxonomy = taxonomy

    def merge(
        self,
        *,
        prev: ShoppingConstraints | None,
        vision: RecognitionResult | None,
        intent: IntentPatch | None,
        correction: RecognitionCorrection | None,
        new_subject: bool,
        turn_id: str,
        subject_id: str | None = None,
    ) -> MergeResult:
        prev = prev or ShoppingConstraints()
        result = MergeResult(constraints=self._base(prev, new_subject))

        # 应用 clear_fields 基线：历史 clear 字段保持清空（§8.1 底部）
        for f in prev.clear_fields:
            if f not in result.constraints.clear_fields:
                result.constraints.clear_fields.append(f)

        # 按 §8.1 优先级从弱到强依次应用：图片 < 用户文本 < 用户修正，
        # 保证高优先级来源覆盖低优先级来源。
        if vision is not None:
            self._apply_vision(result, vision, turn_id)
        if intent is not None:
            self._apply_intent(result, intent, turn_id, subject_id)
        if correction is not None:
            self._apply_correction(result, correction, turn_id)

        self._detect_conflicts(result, vision, intent, correction, turn_id)
        self._validate_taxonomy_attributes(result, turn_id)
        return result

    # ------------------------------------------------------------------
    def _base(self, prev: ShoppingConstraints, new_subject: bool) -> ShoppingConstraints:
        """构造合并基础：新 subject 时清商品字段，保留通用偏好。"""
        if not new_subject:
            return prev.model_copy(deep=True)
        base = ShoppingConstraints()
        for name in _PRESERVED_ON_NEW_SUBJECT:
            sv_obj = getattr(prev, name)
            if isinstance(sv_obj, SourcedValue) and sv_obj.value is not None:
                setattr(base, name, sv_obj.model_copy(deep=True))
        base.clear_fields = list(prev.clear_fields)
        return base

    def _apply_correction(
        self, result: MergeResult, correction: RecognitionCorrection, turn_id: str
    ) -> None:
        c = result.constraints
        clear = set(correction.clear_fields)
        # clear_fields 中的字段不允许低优先级补回
        for f in clear:
            if f not in c.clear_fields:
                c.clear_fields.append(f)
            setattr(c, f, SourcedValue())

        if correction.category_id is not None:
            cat = self._taxonomy.get_category(correction.category_id)
            if cat is None:
                raise ConstraintConflictError_(f"未知品类 {correction.category_id}")
            c.category_id = _sv(
                cat.category_id, ConstraintSource.USER_CORRECTION, turn_id, locked=True
            )
            c.category_name = _sv(
                cat.category_name, ConstraintSource.USER_CORRECTION, turn_id, locked=True
            )
            self._clear_field(c, "category_name", correction.clear_fields)
        if correction.brand is not None:
            brand = self._taxonomy.normalize_brand(correction.brand)
            c.brand = _sv(
                brand or correction.brand, ConstraintSource.USER_CORRECTION, turn_id, locked=True
            )
            self._clear_field(c, "brand", correction.clear_fields)
        if correction.model is not None:
            model = self._taxonomy.normalize_model(correction.model, c.category_id.value)
            c.model = _sv(
                model or correction.model, ConstraintSource.USER_CORRECTION, turn_id, locked=True
            )
            self._clear_field(c, "model", correction.clear_fields)
        for key, value in correction.attributes.items():
            if value is None:
                attrs = dict(c.attributes.value or {})
                attrs.pop(key, None)
                c.attributes = (
                    _sv(attrs, ConstraintSource.USER_CORRECTION, turn_id, locked=True)
                    if attrs
                    else SourcedValue()
                )
            else:
                attrs = dict(c.attributes.value or {})
                attrs[key] = value
                c.attributes = _sv(attrs, ConstraintSource.USER_CORRECTION, turn_id, locked=True)

    def _apply_intent(
        self, result: MergeResult, intent: IntentPatch, turn_id: str, subject_id: str | None
    ) -> None:
        c = result.constraints
        clear = set(intent.clear_fields)
        for f in clear:
            if f not in c.clear_fields:
                c.clear_fields.append(f)
            setattr(c, f, SourcedValue())

        if intent.category_id is not None:
            cat_id, cat_name = self._taxonomy.resolve_category(intent.category_id)
            if cat_id is None:
                raise ConstraintConflictError_(f"未知品类 {intent.category_id}")
            c.category_id = _sv(cat_id, ConstraintSource.USER_TEXT, turn_id, locked=True)
            c.category_name = _sv(cat_name, ConstraintSource.USER_TEXT, turn_id, locked=True)
        if intent.brand is not None:
            brand = self._taxonomy.normalize_brand(intent.brand)
            c.brand = _sv(brand or intent.brand, ConstraintSource.USER_TEXT, turn_id, locked=True)
        if intent.model is not None:
            model = self._taxonomy.normalize_model(intent.model, c.category_id.value)
            c.model = _sv(model or intent.model, ConstraintSource.USER_TEXT, turn_id, locked=True)
        if intent.min_price is not None:
            c.min_price = _sv(intent.min_price, ConstraintSource.USER_TEXT, turn_id, locked=True)
        if intent.max_price is not None:
            c.max_price = _sv(intent.max_price, ConstraintSource.USER_TEXT, turn_id, locked=True)
        if intent.colors is not None:
            c.colors = _sv(
                list(dict.fromkeys(intent.colors)), ConstraintSource.USER_TEXT, turn_id, locked=True
            )
        if intent.platforms is not None:
            c.platforms = _sv(
                list(dict.fromkeys(intent.platforms)),
                ConstraintSource.USER_TEXT,
                turn_id,
                locked=True,
            )
        if intent.min_rating is not None:
            c.min_rating = _sv(intent.min_rating, ConstraintSource.USER_TEXT, turn_id, locked=True)
        if intent.sort_by is not None:
            c.sort_by = _sv(intent.sort_by, ConstraintSource.USER_TEXT, turn_id, locked=True)
        if intent.preferences is not None:
            self._merge_preferences(c, intent.preferences, turn_id)
        if intent.cancelled_preferences:
            self._cancel_preferences(c, intent.cancelled_preferences, turn_id)
        if intent.attributes:
            self._merge_attributes(c, intent.attributes, turn_id)

    def _apply_vision(self, result: MergeResult, vision: RecognitionResult, turn_id: str) -> None:
        c = result.constraints
        # 被 clear 的字段不允许低优先级补回；
        # 已由用户修正/用户文本/用户选项确定的字段（§8.1 优先级 1–3）不允许被当前图片覆盖
        if (
            vision.category_id
            and "category_id" not in c.clear_fields
            and c.category_id.source not in _HIGHER_THAN_VISION
        ):
            cat_id, cat_name = self._taxonomy.resolve_category(vision.category_id)
            if cat_id:
                conf = vision.field_confidences.get("category_id", vision.overall_confidence)
                c.category_id = _sv(cat_id, ConstraintSource.VISION, turn_id, confidence=conf)
                c.category_name = _sv(
                    cat_name or vision.category_name,
                    ConstraintSource.VISION,
                    turn_id,
                    confidence=conf,
                )
        if (
            vision.brand
            and "brand" not in c.clear_fields
            and c.brand.source not in _HIGHER_THAN_VISION
        ):
            brand = self._taxonomy.normalize_brand(vision.brand)
            conf = vision.field_confidences.get("brand", vision.overall_confidence)
            c.brand = _sv(brand or vision.brand, ConstraintSource.VISION, turn_id, confidence=conf)
        if (
            vision.model
            and "model" not in c.clear_fields
            and c.model.source not in _HIGHER_THAN_VISION
        ):
            model = self._taxonomy.normalize_model(vision.model, c.category_id.value)
            conf = vision.field_confidences.get("model", vision.overall_confidence)
            c.model = _sv(model or vision.model, ConstraintSource.VISION, turn_id, confidence=conf)
        if (
            vision.attributes
            and "attributes" not in c.clear_fields
            and c.attributes.source not in _HIGHER_THAN_VISION
        ):
            c.attributes = _sv(
                dict(vision.attributes),
                ConstraintSource.VISION,
                turn_id,
                confidence=vision.overall_confidence,
            )

    # ------------------------------------------------------------------
    def _merge_preferences(
        self, c: ShoppingConstraints, prefs: list[Preference], turn_id: str
    ) -> None:
        current = list(c.preferences.value or []) if c.preferences.value is not None else []
        merged = list(dict.fromkeys(current + [p for p in prefs]))
        c.preferences = _sv(merged, ConstraintSource.USER_TEXT, turn_id, locked=True)

    def _cancel_preferences(
        self, c: ShoppingConstraints, cancelled: list[Preference], turn_id: str
    ) -> None:
        current = list(c.preferences.value or []) if c.preferences.value is not None else []
        merged = [p for p in current if p not in cancelled]
        if merged:
            c.preferences = _sv(merged, ConstraintSource.USER_TEXT, turn_id, locked=True)
        else:
            c.preferences = SourcedValue()

    def _merge_attributes(
        self, c: ShoppingConstraints, patch: dict[str, str | None], turn_id: str
    ) -> None:
        current = dict(c.attributes.value or {}) if c.attributes.value is not None else {}
        for key, value in patch.items():
            if value is None:
                current.pop(key, None)
            else:
                current[key] = value
        c.attributes = (
            _sv(current, ConstraintSource.USER_TEXT, turn_id, locked=True)
            if current
            else SourcedValue()
        )

    # ------------------------------------------------------------------
    def _detect_conflicts(
        self,
        result: MergeResult,
        vision: RecognitionResult | None,
        intent: IntentPatch | None,
        correction: RecognitionCorrection | None,
        turn_id: str,
    ) -> None:
        c = result.constraints
        # 1. 当前文本明确品类与当前图片高置信品类不同（§8.3）
        if vision is not None and intent is not None and intent.category_id:
            vision_cat = vision.category_id
            cat_conf = vision.field_confidences.get("category_id", vision.overall_confidence)
            resolved_intent, _ = self._taxonomy.resolve_category(intent.category_id)
            resolved_vision, _ = self._taxonomy.resolve_category(vision_cat)
            if resolved_intent and resolved_vision and resolved_intent != resolved_vision:
                if cat_conf >= CATEGORY_CONFLICT_CONFIDENCE_THRESHOLD:
                    result.conflicts.append(
                        ConstraintConflict(
                            reason_code="CATEGORY_CONFLICT",
                            field="category_id",
                            message=(
                                "您说的品类与图片识别品类不同："
                                f"图片更像{vision.category_name or vision_cat}"
                            ),
                            a_value=resolved_intent,
                            b_value=resolved_vision,
                        )
                    )
                else:
                    result.notices.append(
                        f"图片识别品类（{vision_cat}）置信度较低，已按您的文字描述采用"
                    )
        # 2. 用户修正品牌与当前文本明确品牌不同
        if correction is not None and intent is not None and correction.brand and intent.brand:
            a = self._taxonomy.normalize_brand(correction.brand)
            b = self._taxonomy.normalize_brand(intent.brand)
            if a and b and a != b:
                result.conflicts.append(
                    ConstraintConflict(
                        reason_code="BRAND_CONFLICT",
                        field="brand",
                        message=f"您修正的品牌（{correction.brand}）与文字中提到的品牌（{intent.brand}）不一致",
                        a_value=correction.brand,
                        b_value=intent.brand,
                    )
                )
        # 3. 同一轮出现两个互斥型号（文本 vs 修正）
        if correction is not None and intent is not None and correction.model and intent.model:
            a = self._taxonomy.normalize_model(correction.model, c.category_id.value)
            b = self._taxonomy.normalize_model(intent.model, c.category_id.value)
            if a and b and a != b:
                result.conflicts.append(
                    ConstraintConflict(
                        reason_code="MODEL_CONFLICT",
                        field="model",
                        message=f"您修正的型号（{correction.model}）与文字中的型号（{intent.model}）互斥",
                        a_value=correction.model,
                        b_value=intent.model,
                    )
                )
        # 4. min_price > max_price
        lo = c.min_price.value
        hi = c.max_price.value
        if lo is not None and hi is not None and lo > hi:
            result.conflicts.append(
                ConstraintConflict(
                    reason_code="PRICE_RANGE_CONFLICT",
                    field="min_price",
                    message=f"价格区间无效：最低价 {lo} 大于最高价 {hi}",
                    a_value=lo,
                    b_value=hi,
                )
            )

    def _validate_taxonomy_attributes(self, result: MergeResult, turn_id: str) -> None:
        """用户指定的属性必须属于 taxonomy 中该品类的属性 schema（§8.3）。"""
        c = result.constraints
        category_id = c.category_id.value
        if not category_id or not c.attributes.value:
            return
        attrs = c.attributes.value
        invalid = [
            k for k in attrs if not self._taxonomy.validate_attribute(category_id, k, str(attrs[k]))
        ]
        if invalid:
            result.conflicts.append(
                ConstraintConflict(
                    reason_code="UNKNOWN_ATTRIBUTE",
                    field="attributes",
                    message=f"属性 {invalid} 不属于品类 {category_id} 的属性 schema",
                    a_value=invalid,
                )
            )

    @staticmethod
    def _clear_field(c: ShoppingConstraints, name: str, clear_fields: list[str]) -> None:
        if name in clear_fields:
            setattr(c, name, SourcedValue())


class ClarificationBuilder:
    """澄清策略（§16）：一次只问一个主问题，优先级固定。模板生成，不依赖 LLM。"""

    PRIORITY = (
        ("MISSING_CATEGORY", "缺少商品品类"),
        ("CONFLICT", "识别与文本冲突"),
        ("IDENTITY_MISSING", "关键属性缺失"),
        ("PRICE_RANGE_CONFLICT", "价格区间冲突"),
    )

    def build(
        self,
        *,
        question_id: str,
        subject_id: str,
        turn_id: str,
        reason_code: str,
        missing_fields: list[str] | None = None,
        conflict: ConstraintConflict | None = None,
        taxonomy: Taxonomy | None = None,
    ) -> Clarification:
        if reason_code == "MISSING_CATEGORY":
            question = (
                "请问这是什么商品？请告诉我品类，例如：耳机、运动鞋、吹风机、背包或智能手表。"
            )
            options = []
            if taxonomy is not None:
                options = [
                    ClarificationOption(
                        option_id=f"cat:{cat.category_id}",
                        label=cat.category_name,
                        applies_to="category_id",
                    )
                    for cat in taxonomy.categories()
                ]
            missing_fields = ["category_id"]
        elif reason_code == "CONFLICT" and conflict is not None:
            question = f"检测到信息冲突：{conflict.message}。请确认以哪个为准？"
            options = [
                ClarificationOption(
                    option_id=f"conf:{conflict.reason_code}:a",
                    label=f"采用：{conflict.a_value}",
                    applies_to=conflict.field,
                ),
                ClarificationOption(
                    option_id=f"conf:{conflict.reason_code}:b",
                    label=f"采用：{conflict.b_value}",
                    applies_to=conflict.field,
                ),
            ]
            missing_fields = [conflict.field]
        elif reason_code == "IDENTITY_MISSING":
            question = "请补充该商品的关键规格，以便准确比价："
            options = []
            missing_fields = missing_fields or []
        elif reason_code == "PRICE_RANGE_CONFLICT":
            question = f"价格区间无效：{conflict.message if conflict else ''}。请重新设置预算。"
            options = []
            missing_fields = ["min_price", "max_price"]
        else:
            question = "请补充必要信息以继续比价。"
            options = []
            missing_fields = missing_fields or []

        return Clarification(
            question_id=question_id,
            question=question,
            reason_code=reason_code,
            missing_fields=missing_fields,
            options=options,
            subject_id=subject_id,
            turn_id=turn_id,
        )
