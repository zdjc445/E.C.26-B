"""同款与 SKU 链路使用的自包含领域模型。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Offer:
    offer_id: str
    platform: str
    title: str = ""
    source_product_id: str | None = None
    source_updated_at: str | None = None
    category_id: str | None = None
    brand: str | None = None
    model: str | None = None
    same_item_key: str | None = None
    identity_attributes: Mapping[str, str] = field(default_factory=dict)
    variant_attributes: Mapping[str, str] = field(default_factory=dict)
    price: float | None = None
    shipping_fee: float | None = None
    coupon_amount: float | None = None
    shop_id: str | None = None


@dataclass(frozen=True)
class NormalizedCandidate:
    offer_id: str
    offer: Offer
    normalized_category_id: str | None = None
    normalized_brand: str | None = None
    normalized_model: str | None = None
    normalized_identity: dict[str, str] = field(default_factory=dict)
    normalized_variant: dict[str, str] = field(default_factory=dict)
    normalization_failures: list[str] = field(default_factory=list)
    recall_score: float = 0.0


@dataclass(frozen=True)
class PairResult:
    a_id: str
    b_id: str
    score: float
    title_similarity: float | None = None
    identity_overlap: float | None = None
    image_similarity: float | None = None
    source_key_signal: float = 0.0
    hard_conflicts: list[str] = field(default_factory=list)
    verdict: str = "different"


@dataclass(frozen=True)
class SkuGroup:
    group_id: str
    spu_id: str
    sku_signature: str | None = None
    sku_attributes: dict[str, str] = field(default_factory=dict)
    offers: list[Offer] = field(default_factory=list)
    min_price: float | None = None
    max_price: float | None = None
    average_price: float | None = None
    min_price_offer_id: str | None = None
    offer_count: int = 0
    platform_count: int = 0
    price_freshness: float | None = None
    match_confidence: float = 0.0
    missing_sku_attributes: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    category_id: str | None = None
    category_name: str | None = None
    brand: str | None = None
    model: str | None = None
    title: str | None = None
