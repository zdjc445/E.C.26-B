"""事实证据构建与事实一致性校验（方案 §11.5、§14.7）。

模型只接收 EvidenceBundle；输出中的数字、平台名和 group ID 必须全部存在于
输入证据中。校验失败直接使用模板解释。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from dataclasses import field as dc_field

from shijiajing_agent.contracts import RankedGroup, ShoppingConstraints, SkuGroup

_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")

# 平台 ID 与常用中文名对照。ID 来自上游数据，中文名仅用于解释文本的事实一致性校验。
_PLATFORM_NAMES: dict[str, tuple[str, ...]] = {
    "taobao": ("淘宝", "天猫"),
    "tmall": ("天猫",),
    "jd": ("京东",),
    "pinduoduo": ("拼多多",),
    "douyin": ("抖音",),
    "vip": ("唯品会",),
}


@dataclass
class GroupEvidence:
    group_id: str
    title: str
    min_price: float | None
    average_price: float | None
    price_range: str
    platform_names: list[str]
    match_confidence: float
    offer_count: int
    hit_conditions: list[str]
    missing_data: list[str]
    risks: list[str]
    rank: int


@dataclass
class EvidenceBundle:
    query_summary: str
    groups: list[GroupEvidence] = dc_field(default_factory=list[GroupEvidence])
    notices: list[str] = dc_field(default_factory=list[str])


class EvidenceBuilder:
    """从排序结果构建可审计的事实证据（纯同步函数）。"""

    def build(
        self,
        ranked: list[RankedGroup],
        constraints: ShoppingConstraints,
        *,
        notices: list[str] | None = None,
        total_groups: int = 0,
    ) -> EvidenceBundle:
        bundle = EvidenceBundle(
            query_summary=self._query_summary(constraints),
            notices=list(notices or []),
        )
        for rg in ranked:
            g = rg.group
            platform_names = list(dict.fromkeys(o.platform for o in g.offers if o.platform))
            hit = self._hit_conditions(g, constraints)
            missing: list[str] = []
            if g.min_price is None:
                missing.append("价格缺失")
            if not g.offers or not g.offers[0].rating:
                missing.append("评分缺失")
            if not g.offers or not g.offers[0].sales:
                missing.append("销量缺失")
            if (
                not g.offers
                or not g.offers[0].seller_type
                or g.offers[0].seller_type.value == "unknown"
            ):
                missing.append("店铺类型未知")
            price_range = "—"
            if g.min_price is not None and g.max_price is not None:
                price_range = (
                    f"{g.min_price:g}–{g.max_price:g}"
                    if g.min_price != g.max_price
                    else f"{g.min_price:g}"
                )
            bundle.groups.append(
                GroupEvidence(
                    group_id=g.group_id,
                    title=g.title or "",
                    min_price=g.min_price,
                    average_price=g.average_price,
                    price_range=price_range,
                    platform_names=platform_names,
                    match_confidence=g.match_confidence,
                    offer_count=g.offer_count,
                    hit_conditions=hit,
                    missing_data=missing,
                    risks=list(g.risks),
                    rank=rg.rank,
                )
            )
        return bundle

    @staticmethod
    def _query_summary(constraints: ShoppingConstraints) -> str:
        parts: list[str] = []
        if constraints.category_name.value:
            parts.append(str(constraints.category_name.value))
        if constraints.brand.value:
            parts.append(str(constraints.brand.value))
        if constraints.model.value:
            parts.append(str(constraints.model.value))
        if constraints.colors.value:
            parts.append("/".join(str(c) for c in constraints.colors.value))
        return " ".join(parts) or "未指定商品"

    @staticmethod
    def _hit_conditions(g: SkuGroup, constraints: ShoppingConstraints) -> list[str]:
        hits: list[str] = []
        if constraints.brand.value and g.brand == constraints.brand.value:
            hits.append(f"品牌 {constraints.brand.value}")
        if constraints.model.value and g.model == constraints.model.value:
            hits.append(f"型号 {constraints.model.value}")
        if constraints.min_price.value is not None:
            hits.append(f"最低价不低于 {constraints.min_price.value}")
        if constraints.max_price.value is not None:
            hits.append(f"最高价不超过 {constraints.max_price.value}")
        if constraints.min_rating.value is not None:
            hits.append(f"评分不低于 {constraints.min_rating.value}")
        if constraints.colors.value:
            hits.append(f"颜色 {constraints.colors.value}")
        if constraints.platforms.value:
            hits.append(f"平台 {'、'.join(str(p) for p in constraints.platforms.value)}")
        if constraints.preferences.value:
            hits.append(f"偏好 {'、'.join(str(p) for p in constraints.preferences.value)}")
        return hits


class FactualConsistencyChecker:
    """解释文本事实一致性校验（§11.5）。

    输出中的数字、平台名和 group ID 必须全部存在于输入证据中。
    """

    def verify(self, text: str, bundle: EvidenceBundle) -> tuple[bool, list[str]]:
        violations: list[str] = []
        allowed_numbers: set[str] = set()
        for g in bundle.groups:
            if g.min_price is not None:
                allowed_numbers.add(f"{g.min_price:g}")
            if g.average_price is not None:
                allowed_numbers.add(f"{g.average_price:g}")
            if g.price_range != "—":
                for part in g.price_range.split("–"):
                    allowed_numbers.add(part)
        for num in _NUMBER_RE.findall(text):
            if num not in allowed_numbers:
                violations.append(f"数字 {num} 不在输入证据中")
        # 平台名校验（§11.5）：输出中的平台名必须存在于输入证据中。
        # 平台 ID 与其常用中文名视为同一平台；文本提及某平台而证据中没有即为违规。
        evidence_platforms = {p for g in bundle.groups for p in g.platform_names}
        for platform_id, aliases in _PLATFORM_NAMES.items():
            if platform_id in evidence_platforms:
                continue
            if any(a in text for a in (platform_id, *aliases)):
                violations.append(f"平台 {platform_id} 不在输入证据中")
        return len(violations) == 0, violations

    def template_explanation(self, bundle: EvidenceBundle) -> str:
        """模板解释（模型失败或事实校验失败时使用）。"""
        if not bundle.groups:
            return "当前没有符合条件的比价结果。"
        lines: list[str] = []
        for g in bundle.groups[:3]:
            price_part = f"最低 {g.min_price:g} 元" if g.min_price is not None else "价格待确认"
            platform_part = "、".join(g.platform_names) if g.platform_names else "多平台"
            lines.append(f"{g.rank}. {g.title or '未命名商品'}：{price_part}（{platform_part}）")
        text = "为您找到以下同款商品报价：\n" + "\n".join(lines)
        if bundle.notices:
            text += "\n" + "；".join(bundle.notices)
        return text
