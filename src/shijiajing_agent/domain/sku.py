"""SKU 拆分与价格聚合（方案 §14.6–§14.7）。

对每个 SPU，按 taxonomy 声明的 ``variant_attributes`` 生成规范化 ``sku_signature``。
签名包含属性名和标准值，并按属性名排序。缺少关键 SKU 属性时该 Offer 单独成组、
``match_confidence`` 降低并附加风险提示。只有相同 SKU 进入同一个比价组。

全部为同步纯函数。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC

from shijiajing_agent.contracts import NormalizedCandidate, Offer, SkuGroup
from shijiajing_agent.domain.taxonomy import Taxonomy


@dataclass(frozen=True)
class PriceAggregation:
    """SKU 组价格聚合结果（§14.7）。"""

    min_price: float | None
    max_price: float | None
    average_price: float | None
    min_price_offer_id: str | None
    platform_count: int
    price_freshness: float | None


class SkuSplitter:
    """§14.6–14.7 SKU 拆分与价格聚合。"""

    def __init__(self, taxonomy: Taxonomy, *, dynamic: bool = False) -> None:
        self._taxonomy = taxonomy
        self._dynamic = dynamic

    def split_spu(
        self,
        spu_members: list[NormalizedCandidate],
        spu_id: str,
    ) -> list[SkuGroup]:
        """按 taxonomy variant_attributes 生成规范化 sku_signature 并分组。"""
        if not spu_members:
            return []
        category_id = spu_members[0].normalized_category_id
        dynamic_mode = self._dynamic or any(member.dynamic_schema_id for member in spu_members)
        if dynamic_mode:
            variant_keys = sorted(
                {
                    key
                    for member in spu_members
                    for key in member.dynamic_variant_keys
                }
            )
        else:
            variant_keys = self._taxonomy.variant_attributes(category_id) if category_id else []
        brand = spu_members[0].normalized_brand
        model = spu_members[0].normalized_model

        buckets: dict[str, list[NormalizedCandidate]] = {}
        singles: list[NormalizedCandidate] = []
        for m in spu_members:
            signature = self._sku_signature(m, variant_keys, dynamic_mode=dynamic_mode)
            if signature is None:
                singles.append(m)
            else:
                buckets.setdefault(signature, []).append(m)

        groups: list[SkuGroup] = []
        for signature, members in buckets.items():
            groups.append(
                self._build_group(
                    members,
                    spu_id,
                    signature,
                    sku_attributes=self._signature_attrs(signature),
                    category_id=category_id,
                    brand=brand,
                    model=model,
                    missing_attrs=[],
                    risks=[],
                )
            )
        # 缺少关键 SKU 属性的 Offer 单独成组（§14.6）
        for m in singles:
            groups.append(
                self._build_group(
                    [m],
                    spu_id,
                    None,
                    sku_attributes=dict(m.normalized_variant),
                    category_id=category_id,
                    brand=brand,
                    model=model,
                    missing_attrs=[k for k in variant_keys if k not in m.normalized_variant],
                    risks=[
                        "动态 Schema 不完整，未与其他报价直接合并"
                        if dynamic_mode
                        else "关键销售属性缺失，未与其他报价直接合并"
                    ],
                )
            )
        return groups

    def _sku_signature(
        self,
        m: NormalizedCandidate,
        variant_keys: list[str],
        *,
        dynamic_mode: bool = False,
    ) -> str | None:
        """签名包含属性名和标准值，按属性名排序。缺失关键属性 → None。"""
        if dynamic_mode and m.offer.sku_key:
            return f"__authority_sku_key__={m.offer.sku_key}"
        if not variant_keys:
            # 没有可靠动态 variant schema 时，多个 Offer 不能自动断言为同一精确 SKU。
            return "" if not dynamic_mode else None
        parts: list[str] = []
        for key in sorted(variant_keys):
            if key not in m.normalized_variant:
                return None
            parts.append(f"{key}={m.normalized_variant[key]}")
        return "|".join(parts)

    @staticmethod
    def _signature_attrs(signature: str) -> dict[str, str]:
        attrs: dict[str, str] = {}
        for part in signature.split("|"):
            if "=" in part:
                k, _, v = part.partition("=")
                if k == "__authority_sku_key__":
                    continue
                attrs[k] = v
        return attrs

    def _build_group(
        self,
        members: list[NormalizedCandidate],
        spu_id: str,
        signature: str | None,
        *,
        sku_attributes: dict[str, str],
        category_id: str | None,
        brand: str | None,
        model: str | None,
        missing_attrs: list[str],
        risks: list[str],
    ) -> SkuGroup:
        offers = self._dedup_offers([m.offer for m in members])
        agg = self._aggregate_prices(offers)
        confidence = self._cluster_confidence(members)
        if missing_attrs:
            confidence *= 0.9
        sku_suffix = hashlib.sha256((signature or "single").encode()).hexdigest()[:10]
        cat = self._taxonomy.get_category(category_id) if category_id else None
        return SkuGroup(
            group_id=f"{spu_id}:{sku_suffix}",
            spu_id=spu_id,
            sku_signature=signature,
            sku_attributes=sku_attributes,
            offers=offers,
            min_price=agg.min_price,
            max_price=agg.max_price,
            average_price=agg.average_price,
            min_price_offer_id=agg.min_price_offer_id,
            offer_count=len(offers),
            platform_count=agg.platform_count,
            price_freshness=agg.price_freshness,
            match_confidence=round(confidence, 4),
            missing_sku_attributes=missing_attrs,
            risks=risks,
            category_id=category_id,
            category_name=cat.category_name if cat else None,
            brand=brand,
            model=model,
            title=offers[0].title if offers else None,
        )

    @staticmethod
    def _cluster_confidence(members: list[NormalizedCandidate]) -> float:
        if not members:
            return 0.0
        return max(0.0, min(1.0, sum(m.recall_score for m in members) / len(members)))

    @staticmethod
    def _dedup_offers(offers: list[Offer]) -> list[Offer]:
        """§14.7 先按 platform + shop_id + source_product_id 去重，保留 source_updated_at 最新。"""
        seen: dict[tuple[str, str, str], Offer] = {}
        for o in offers:
            key = (o.platform, o.shop_id or "", o.source_product_id or "")
            prev = seen.get(key)
            if prev is None:
                seen[key] = o
                continue
            if (o.source_updated_at or "") > (prev.source_updated_at or ""):
                seen[key] = o
        return list(seen.values())

    @staticmethod
    def _aggregate_prices(offers: list[Offer]) -> PriceAggregation:
        """§14.7 payable_price = price - coupon_amount + shipping_fee（字段真实存在时）。"""
        prices: list[float] = []
        min_offer_id: str | None = None
        min_price: float | None = None
        for o in offers:
            if o.price is None:
                continue
            payable = o.price
            if o.coupon_amount is not None:
                payable -= o.coupon_amount
            if o.shipping_fee is not None:
                payable += o.shipping_fee
            prices.append(payable)
            if min_price is None or payable < min_price:
                min_price = payable
                min_offer_id = o.offer_id
        if not prices:
            return PriceAggregation(None, None, None, None, 0, None)
        # price_freshness：价格新鲜度（0–1），有 source_updated_at 的报价按 30 天衰减
        freshness = SkuSplitter._compute_freshness(offers)
        return PriceAggregation(
            min_price=min_price,
            max_price=max(prices),
            average_price=sum(prices) / len(prices),
            min_price_offer_id=min_offer_id,
            platform_count=len({o.platform for o in offers}),
            price_freshness=freshness,
        )

    @staticmethod
    def _compute_freshness(offers: list[Offer]) -> float | None:
        from datetime import datetime

        scored = 0
        total = 0.0
        for o in offers:
            if not o.source_updated_at:
                continue
            try:
                ts = datetime.fromisoformat(o.source_updated_at.replace("Z", "+00:00"))
            except ValueError:
                continue
            age_days = (datetime.now(UTC) - ts).total_seconds() / 86400
            total += max(0.0, 1.0 - age_days / 30.0)
            scored += 1
        if scored == 0:
            return None
        return round(total / scored, 4)


def spu_id_for(members: list[NormalizedCandidate]) -> str:
    ids = sorted(m.offer_id for m in members)
    digest = hashlib.sha256(json.dumps(ids, ensure_ascii=False).encode()).hexdigest()[:12]
    return f"spu:{digest}"
