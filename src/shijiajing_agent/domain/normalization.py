"""字段标准化。

标准化顺序：
1. Unicode 和空白规范化
2. 显式别名映射
3. 单位换算
4. 品牌标准化
5. 型号分隔符和空白标准化
6. 品类属性 schema 校验
7. 原值、标准值和规则版本同时保留

标准化失败时保留原值但不参与硬匹配，并在证据中标记"属性未标准化"。
"""

from __future__ import annotations

import re
import unicodedata

from shijiajing_agent.contracts import NormalizedCandidate, Offer
from shijiajing_agent.domain.taxonomy import Taxonomy

_MODEL_SEPARATORS = re.compile(r"[\s\-_/·]+")
_UNIT_PATTERNS: list[tuple[re.Pattern[str], str, float]] = [
    (re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([Ll]|升)\s*$"), "L", 1.0),
    (re.compile(r"^\s*(\d+(?:\.\d+)?)\s*毫升\s*$"), "L", 0.001),
    (re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(ml|ML)\s*$"), "L", 0.001),
    (re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(w|W|瓦)\s*$"), "W", 1.0),
    (re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(kw|kW|KW|千瓦)\s*$"), "W", 1000.0),
    (re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(h|H|小时)\s*$"), "h", 1.0),
]


def canonical_identity_title(
    category_id: str | None,
    brand: str | None,
    model: str | None,
    identity: dict[str, str],
) -> str | None:
    """用可信身份字段构造匹配标题；没有品牌+型号锚点时保守返回 None。"""

    if not brand or not model:
        return None
    parts = [category_id or "", brand, model]
    parts.extend(f"{key}={identity[key]}" for key in sorted(identity))
    return " ".join(part for part in parts if part)


def build_search_text(
    offer: Offer,
    *,
    category_name: str | None,
    taxonomy: Taxonomy,
) -> str:
    """构造索引检索文本（方案 §13.3）。

    拼接顺序：标准品类名 → 品牌 → 型号 → 标题 → identity attributes →
    variant attributes → 可搜索标签。字段名和值同时进入文本，
    例如“降噪 主动降噪”，提升属性词检索稳定性。
    """
    parts: list[str] = []
    if category_name:
        parts.append(category_name)
    if offer.brand:
        parts.append(offer.brand)
    if offer.model:
        parts.append(offer.model)
    if offer.title:
        parts.append(offer.title)
    for key, value in {**offer.identity_attributes, **offer.variant_attributes}.items():
        parts.append(f"{key} {value}")
    cat = taxonomy.get_category(offer.category_id) if offer.category_id else None
    for key in cat.searchable_attributes if cat else []:
        value = offer.descriptive_attributes.get(key)
        if value:
            parts.append(f"{key} {value}")
    return " ".join(p for p in parts if p)


class TaxonomyNormalizer:
    """Offer/识别结果的字段标准化器（同步纯函数）。"""

    def __init__(self, taxonomy: Taxonomy) -> None:
        self._taxonomy = taxonomy

    def normalize_offer(self, offer: Offer) -> NormalizedCandidate:
        failures: list[str] = []
        category_id = self._taxonomy.resolve_category(offer.category_id)[0]

        brand = self._taxonomy.normalize_brand(offer.brand)
        if offer.brand and not brand:
            failures.append("brand")
        model = self._taxonomy.normalize_model(offer.model, category_id)
        if offer.model and not model:
            failures.append("model")

        identity: dict[str, str] = {}
        for key, raw in offer.identity_attributes.items():
            std = self.normalize_attribute(category_id, key, raw)
            if std is not None:
                identity[key] = std
            elif raw:
                failures.append(f"identity:{key}")
        variant: dict[str, str] = {}
        for key, raw in offer.variant_attributes.items():
            std = self.normalize_attribute(category_id, key, raw)
            if std is not None:
                variant[key] = std
            elif raw:
                failures.append(f"variant:{key}")

        normalized_title = canonical_identity_title(category_id, brand, model, identity)
        normalized_offer = offer.model_copy(
            update={"normalized_title": normalized_title or offer.normalized_title}
        )
        return NormalizedCandidate(
            offer_id=offer.offer_id,
            offer=normalized_offer,
            normalized_category_id=category_id,
            normalized_brand=brand,
            normalized_model=model,
            normalized_identity=identity,
            normalized_variant=variant,
            normalization_failures=failures,
            recall_score=0.0,
        )

    def normalize_recognition(
        self,
        *,
        category_id: str | None,
        brand: str | None,
        model: str | None,
        attributes: dict[str, str] | None,
    ) -> dict[str, object]:
        """识别结果标准化（nodes/normalize_recognition 使用）。未知值置空。"""
        cat_id, cat_name = self._taxonomy.resolve_category(category_id)
        std_brand = self._taxonomy.normalize_brand(brand) if brand else None
        std_model = self._taxonomy.normalize_model(model, cat_id) if model else None
        std_attrs: dict[str, str] = {}
        for key, raw in (attributes or {}).items():
            std = self.normalize_attribute(cat_id, key, raw)
            if std is not None:
                std_attrs[key] = std
        return {
            "category_id": cat_id,
            "category_name": cat_name,
            "brand": std_brand,
            "model": std_model,
            "attributes": std_attrs,
        }

    def normalize_attribute(self, category_id: str | None, key: str, raw: str) -> str | None:
        """规范化单个商品属性，供确定性流程和 LLM 补丁校验共用。"""

        text = unicodedata.normalize("NFKC", raw.strip())
        text = re.sub(r"\s+", " ", text)
        if not text:
            return None
        # 单位换算。
        for pattern, unit, factor in _UNIT_PATTERNS:
            m = pattern.match(text)
            if m:
                num = float(m.group(1)) * factor
                text = f"{num:g}{unit}"
                break
        # 枚举值标准化：允许值与属性 enum 做等价匹配。
        # 存在 enum 白名单但值不匹配时返回 None，由调用方标记"属性未标准化"，
        # 原值保留在原始 Offer 中但不参与硬匹配。
        if category_id:
            schema = self._taxonomy.get_category(category_id)
            if schema:
                attr_schema = schema.attribute_schema.get(key)
                allowed = attr_schema.get("enum") if attr_schema else None
                if allowed:
                    for candidate in allowed:
                        if candidate == text or candidate in text or text in candidate:
                            return candidate
                    return None
        return text

    def _normalize_attribute(self, category_id: str | None, key: str, raw: str) -> str | None:
        """兼容旧调用；新代码使用公开的 ``normalize_attribute``。"""

        return self.normalize_attribute(category_id, key, raw)

    @staticmethod
    def model_equivalent(a: str, b: str) -> bool:
        """型号等价：分隔符与空白标准化后比较。"""

        def norm(s: str) -> str:
            s = unicodedata.normalize("NFKC", s.strip()).upper()
            return _MODEL_SEPARATORS.sub(" ", s)

        return bool(norm(a)) and norm(a) == norm(b)

    @staticmethod
    def title_token_similarity(a: str, b: str) -> float:
        """基于 token 的标题相似度（0–1），用于缺少向量时的降级信号。"""
        import math

        def tokens(s: str) -> set[str]:
            return {
                t for t in re.split(r"\W+", unicodedata.normalize("NFKC", s.lower())) if len(t) >= 2
            }

        ta, tb = tokens(a), tokens(b)
        if not ta or not tb:
            return 0.0
        inter = ta & tb
        return len(inter) / math.sqrt(len(ta) * len(tb))
