"""文本意图规则解析器（方案 §11.3）。

模型失败或输出非法时，规则解析器覆盖以下固定表达：

- 预算上限和下限（元）。
- 颜色。
- 平台（显式别名）。
- 最低评分。
- 价格、销量、评分排序。
- 官方/自营、配送、低价、高评分、高销量偏好。
- taxonomy 中明确注册的品类别名和品牌别名。
- 否定表达与"取消"进入 `clear_fields` / `cancelled_preferences`。

规则表只使用显式配置的别名，不根据大小写或模糊相似度猜测未知品牌。
全部为同步纯函数。
"""

from __future__ import annotations

import re

from shijiajing_agent.contracts import (
    IntentPatch,
    MemoryApplyMode,
    MemoryDirective,
    MemoryOperation,
    Preference,
    SortBy,
)
from shijiajing_agent.domain.taxonomy import Taxonomy

_PRICE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(元|块)?")
_RATING_RE = re.compile(r"(\d(?:\.\d+)?)\s*星")
_COLOR_WORDS = (
    "黑色",
    "白色",
    "灰色",
    "银色",
    "红色",
    "蓝色",
    "绿色",
    "紫色",
    "黄色",
    "金色",
    "粉色",
    "棕色",
    "米色",
    "深空灰",
    "午夜黑",
)

# 平台别名（与解释事实校验同一映射，见 domain/evidence.py）
_PLATFORM_ALIASES: dict[str, str] = {
    "淘宝": "taobao",
    "天猫": "tmall",
    "京东": "jd",
    "拼多多": "pinduoduo",
    "抖音": "douyin",
    "唯品会": "vip",
}


class RuleIntentParser:
    """确定性规则解析。不猜测：只识别显式注册的别名与固定表达。"""

    def __init__(self, taxonomy: Taxonomy) -> None:
        self._taxonomy = taxonomy

    def parse(self, text: str | None) -> IntentPatch:
        text = (text or "").strip()
        patch = IntentPatch()
        if not text:
            return patch

        patch.category_id, patch.category_name = self._resolve_category(text)
        patch.brand = self._resolve_brand(text)

        budget = self._parse_budget(text)
        if budget:
            patch.min_price, patch.max_price = budget

        patch.colors = self._parse_colors(text)
        patch.platforms = self._parse_platforms(text)
        patch.min_rating = self._parse_min_rating(text)
        patch.sort_by = self._parse_sort(text)
        patch.preferences = self._parse_preferences(text)
        patch.cancelled_preferences = self._parse_cancelled_preferences(text)
        patch.clear_fields = self._parse_clear_fields(text)
        patch.negative_terms = self._parse_negative_terms(text)
        patch.memory_directives = self._parse_memory_directives(text)
        return patch

    def _parse_memory_directives(self, text: str) -> list[MemoryDirective]:
        """覆盖固定的显式长期记忆表达；普通购物条件永不产生 directive。"""
        directives: list[MemoryDirective] = []
        if (
            "清空" in text
            and any(token in text for token in ("所有购物偏好", "全部偏好", "所有偏好", "所有记忆"))
        ) or any(token in text for token in ("清除全部偏好", "全部忘掉")):
            return [MemoryDirective(operation=MemoryOperation.CLEAR_OWNER)]

        key = self._memory_key(text)
        if key is None:
            return directives
        scope = "global"
        category = self._resolve_category(text)[0]
        if category:
            scope = f"category:{category}"

        if any(token in text for token in ("忘掉", "忘记", "不要记", "别记")):
            directives.append(
                MemoryDirective(operation=MemoryOperation.FORGET, memory_key=key, scope_key=scope)
            )
            return directives
        if not any(token in text for token in ("记住", "记为", "保存", "以后默认", "以后买")):
            return directives
        value = self._memory_value(key, text)
        if value is None:
            return directives
        mode = (
            MemoryApplyMode.RANKING_PRIOR
            if key in {"preferences"} or "优先" in text
            else MemoryApplyMode.CONSTRAINT_DEFAULT
        )
        if key == "negative_terms":
            mode = MemoryApplyMode.NEGATIVE_PREFERENCE
        try:
            directives.append(
                MemoryDirective(
                    operation=MemoryOperation.UPSERT,
                    memory_key=key,
                    value=value,
                    scope_key=scope,
                    apply_mode=mode,
                )
            )
        except ValueError:
            return []
        return directives

    @staticmethod
    def _memory_key(text: str) -> str | None:
        if "评分" in text and any(token in text for token in ("以上", "不低于", "至少")):
            return "min_rating"
        if "预算" in text or (
            "价格" in text and any(token in text for token in ("不超过", "以内", "以下", "上限"))
        ):
            return "max_price"
        if "平台" in text or any(alias in text for alias in _PLATFORM_ALIASES):
            return "platforms"
        if "颜色" in text or any(color in text for color in _COLOR_WORDS):
            return "colors"
        if "排序" in text or "按价格" in text:
            return "sort_by"
        if any(
            token in text
            for token in ("官方", "自营", "配送快", "低价", "性价比", "高评分", "高销量")
        ):
            return "preferences"
        if any(token in text for token in ("不喜欢", "讨厌", "避开")):
            return "negative_terms"
        return None

    def _memory_value(self, key: str, text: str) -> object | None:
        if key == "max_price":
            lo, hi = self._parse_budget(text)
            if hi is not None:
                return hi
            if lo is not None:
                return lo
        if key == "min_rating":
            return self._parse_min_rating(text)
        if key == "platforms":
            return self._parse_platforms(text)
        if key == "colors":
            return self._parse_colors(text)
        if key == "sort_by":
            return self._parse_sort(text)
        if key == "preferences":
            return self._parse_preferences(text)
        if key == "negative_terms":
            for marker in ("不喜欢", "讨厌", "避开"):
                if marker in text:
                    tail = text.split(marker, 1)[1]
                    tail = re.split(r"[，。,.；;\s]", tail, maxsplit=1)[0].strip()
                    if tail:
                        return [tail]
        return None

    @staticmethod
    def _parse_negative_terms(text: str) -> list[str]:
        for marker in ("不喜欢", "讨厌", "避开"):
            if marker in text:
                tail = text.split(marker, 1)[1]
                term = re.split(r"[，。,.；;\s]", tail, maxsplit=1)[0].strip()
                if term:
                    return [term]
        return []

    # ------------------------------------------------------------------
    def _resolve_category(self, text: str) -> tuple[str | None, str | None]:
        for cat in self._taxonomy.categories():
            names = [cat.category_id, cat.category_name, *cat.aliases]
            for name in names:
                if name and name in text:
                    return cat.category_id, cat.category_name
        return None, None

    def _resolve_brand(self, text: str) -> str | None:
        for alias, canonical in self._taxonomy.all_brand_aliases().items():
            if alias and alias in text:
                return canonical
        return None

    def _parse_budget(self, text: str) -> tuple[float | None, float | None]:
        lo: float | None = None
        hi: float | None = None
        # 完整区间："100到200元之间" / "100-200" / "100~200"
        for pattern in (
            r"(\d+(?:\.\d+)?)\s*(?:到|至|~|-)\s*(\d+(?:\.\d+)?)\s*元",
            r"(\d+(?:\.\d+)?)\s*(?:到|至|~)\s*(\d+(?:\.\d+)?)",
        ):
            m = re.search(pattern, text)
            if m:
                lo = float(m.group(1))
                hi = float(m.group(2))
                return lo, hi
        # 上限："不超过/以内/以下/预算内 X 元"（前缀式）
        for word in ("不超过", "以内", "以下", "预算内"):
            m = re.search(rf"{word}\s*{_PRICE_RE.pattern}", text)
            if m:
                return None, float(m.group(1))
        # 上限后缀式："X 元以内 / 预算 X 元以下"（数字在前）
        m = re.search(rf"{_PRICE_RE.pattern}\s*(以内|以下|之内)", text)
        if m:
            return None, float(m.group(1))
        # 下限："不低于/以上/至少 X 元"
        for word in ("不低于", "以上", "至少"):
            m = re.search(rf"{word}\s*{_PRICE_RE.pattern}", text)
            if m:
                return float(m.group(1)), None
        # “预算 1000 元”没有上下限词时，按当前轮/显式记忆的上限处理。
        if "预算" in text:
            m = re.search(r"预算\s*(?:为|是|记为)?\s*" + _PRICE_RE.pattern, text)
            if m:
                return None, float(m.group(1))
        return None, None

    def _parse_colors(self, text: str) -> list[str] | None:
        found = [c for c in _COLOR_WORDS if c in text]
        return found if found else None

    def _parse_platforms(self, text: str) -> list[str] | None:
        found: list[str] = []
        for alias, pid in _PLATFORM_ALIASES.items():
            if alias in text:
                found.append(pid)
        return list(dict.fromkeys(found)) if found else None

    def _parse_min_rating(self, text: str) -> float | None:
        m = _RATING_RE.search(text)
        if m:
            return min(5.0, float(m.group(1)))
        if "评分" in text and ("以上" in text or "不低于" in text):
            m = re.search(r"(\d(?:\.\d+)?)", text)
            if m:
                return min(5.0, float(m.group(1)))
        return None

    def _parse_sort(self, text: str) -> SortBy | None:
        if (
            "最便宜" in text
            or "价格从低到高" in text
            or "按价格排序" in text
            or ("按" in text and "价格" in text and "升序" in text)
        ):
            return SortBy.PRICE_ASC
        if (
            "最贵" in text
            or "价格从高到低" in text
            or "价格倒序" in text
            or ("按" in text and "价格" in text and "降序" in text)
        ):
            return SortBy.PRICE_DESC
        if "按" in text and "评分" in text:
            return SortBy.RATING_DESC
        if "按" in text and "销量" in text:
            return SortBy.SALES_DESC
        return None

    def _parse_preferences(self, text: str) -> list[Preference] | None:
        found: list[Preference] = []
        if "官方" in text or "自营" in text:
            found.append(Preference.OFFICIAL_STORE)
        if "配送" in text or "发货快" in text:
            found.append(Preference.FAST_DELIVERY)
        if "低价" in text or "性价比" in text:
            found.append(Preference.LOWEST_PRICE)
        if "高评分" in text or "好评" in text:
            found.append(Preference.HIGH_RATING)
        if "高销量" in text or "热卖" in text:
            found.append(Preference.HIGH_SALES)
        return found if found else None

    def _parse_cancelled_preferences(self, text: str) -> list[Preference]:
        cancelled: list[Preference] = []
        if "不要" in text or "取消" in text:
            if "低价" in text or "便宜" in text:
                cancelled.append(Preference.LOWEST_PRICE)
            if "配送" in text:
                cancelled.append(Preference.FAST_DELIVERY)
            if "评分" in text:
                cancelled.append(Preference.HIGH_RATING)
            if "销量" in text:
                cancelled.append(Preference.HIGH_SALES)
        return cancelled

    def _parse_clear_fields(self, text: str) -> list[str]:
        """否定表达清空字段："不要颜色/去掉品牌/取消型号" 等。"""
        cleared: list[str] = []
        pairs = (
            ("颜色", "colors"),
            ("品牌", "brand"),
            ("型号", "model"),
            ("预算", "min_price"),
            ("平台", "platforms"),
            ("评分", "min_rating"),
        )
        for word, field in pairs:
            if (f"不要{word}" in text) or (f"去掉{word}" in text) or (f"取消{word}" in text):
                cleared.append(field)
        return cleared
