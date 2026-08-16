"""SKU 拆分、报价去重与价格聚合。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime

from product_matching.models import NormalizedCandidate, Offer, SkuGroup
from product_matching.taxonomy import Taxonomy


@dataclass(frozen=True)
class PriceAggregation:
    min_price: float | None
    max_price: float | None
    average_price: float | None
    min_price_offer_id: str | None
    platform_count: int
    price_freshness: float | None


class SkuSplitter:
    def __init__(self, taxonomy: Taxonomy) -> None:
        self._taxonomy = taxonomy

    def split_spu(
        self,
        spu_members: list[NormalizedCandidate],
        spu_id: str,
    ) -> list[SkuGroup]:
        if not spu_members:
            return []
        category_id = spu_members[0].normalized_category_id
        variant_keys = self._taxonomy.variant_attributes(category_id) if category_id else []
        brand = spu_members[0].normalized_brand
        model = spu_members[0].normalized_model

        buckets: dict[str, list[NormalizedCandidate]] = {}
        singles: list[NormalizedCandidate] = []
        for member in spu_members:
            signature = self._sku_signature(member, variant_keys)
            if signature is None:
                singles.append(member)
            else:
                buckets.setdefault(signature, []).append(member)

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
        for member in singles:
            groups.append(
                self._build_group(
                    [member],
                    spu_id,
                    None,
                    sku_attributes=dict(member.normalized_variant),
                    category_id=category_id,
                    brand=brand,
                    model=model,
                    missing_attrs=[
                        key for key in variant_keys if key not in member.normalized_variant
                    ],
                    risks=["关键销售属性缺失，未与其他报价直接合并"],
                )
            )
        return groups

    @staticmethod
    def _sku_signature(member: NormalizedCandidate, variant_keys: list[str]) -> str | None:
        if not variant_keys:
            return ""
        parts: list[str] = []
        for key in sorted(variant_keys):
            if key not in member.normalized_variant:
                return None
            parts.append(f"{key}={member.normalized_variant[key]}")
        return "|".join(parts)

    @staticmethod
    def _signature_attrs(signature: str) -> dict[str, str]:
        attributes: dict[str, str] = {}
        for part in signature.split("|"):
            if "=" in part:
                key, _, value = part.partition("=")
                attributes[key] = value
        return attributes

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
        offers = self._dedup_offers([member.offer for member in members])
        aggregation = self._aggregate_prices(offers)
        confidence = self._cluster_confidence(members)
        if missing_attrs:
            confidence *= 0.9
        suffix_source = (
            f"single:{members[0].offer_id}" if signature is None else signature or "single"
        )
        suffix = hashlib.sha256(suffix_source.encode()).hexdigest()[:10]
        category = self._taxonomy.get_category(category_id) if category_id else None
        return SkuGroup(
            group_id=f"{spu_id}:{suffix}",
            spu_id=spu_id,
            sku_signature=signature,
            sku_attributes=sku_attributes,
            offers=offers,
            min_price=aggregation.min_price,
            max_price=aggregation.max_price,
            average_price=aggregation.average_price,
            min_price_offer_id=aggregation.min_price_offer_id,
            offer_count=len(offers),
            platform_count=aggregation.platform_count,
            price_freshness=aggregation.price_freshness,
            match_confidence=round(confidence, 4),
            missing_sku_attributes=missing_attrs,
            risks=risks,
            category_id=category_id,
            category_name=category.category_name if category else None,
            brand=brand,
            model=model,
            title=offers[0].title if offers else None,
        )

    @staticmethod
    def _cluster_confidence(members: list[NormalizedCandidate]) -> float:
        if not members:
            return 0.0
        average = sum(member.recall_score for member in members) / len(members)
        return max(0.0, min(1.0, average))

    @staticmethod
    def _dedup_offers(offers: list[Offer]) -> list[Offer]:
        seen: dict[tuple[str, str, str], Offer] = {}
        for offer in offers:
            key = (offer.platform, offer.shop_id or "", offer.source_product_id or "")
            previous = seen.get(key)
            if previous is None or (offer.source_updated_at or "") > (
                previous.source_updated_at or ""
            ):
                seen[key] = offer
        return list(seen.values())

    @staticmethod
    def _aggregate_prices(offers: list[Offer]) -> PriceAggregation:
        prices: list[float] = []
        priced_platforms: set[str] = set()
        min_offer_id: str | None = None
        min_price: float | None = None
        for offer in offers:
            if offer.price is None:
                continue
            priced_platforms.add(offer.platform)
            payable = offer.price
            if offer.coupon_amount is not None:
                payable -= offer.coupon_amount
            if offer.shipping_fee is not None:
                payable += offer.shipping_fee
            prices.append(payable)
            if min_price is None or payable < min_price:
                min_price = payable
                min_offer_id = offer.offer_id
        price_freshness = SkuSplitter._compute_freshness(offers)
        if not prices:
            return PriceAggregation(None, None, None, None, 0, price_freshness)
        return PriceAggregation(
            min_price=min_price,
            max_price=max(prices),
            average_price=sum(prices) / len(prices),
            min_price_offer_id=min_offer_id,
            platform_count=len(priced_platforms),
            price_freshness=price_freshness,
        )

    @staticmethod
    def _compute_freshness(offers: list[Offer]) -> float | None:
        scored = 0
        total = 0.0
        for offer in offers:
            if not offer.source_updated_at:
                continue
            try:
                timestamp = datetime.fromisoformat(offer.source_updated_at.replace("Z", "+00:00"))
            except ValueError:
                continue
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=UTC)
            age_days = (datetime.now(UTC) - timestamp).total_seconds() / 86400
            total += max(0.0, 1.0 - age_days / 30.0)
            scored += 1
        return round(total / scored, 4) if scored else None


def spu_id_for(members: list[NormalizedCandidate]) -> str:
    offer_ids = sorted(member.offer_id for member in members)
    digest = hashlib.sha256(json.dumps(offer_ids, ensure_ascii=False).encode()).hexdigest()[:12]
    return f"spu:{digest}"
