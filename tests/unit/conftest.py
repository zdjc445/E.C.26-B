"""领域层单元测试公共夹具。"""

from __future__ import annotations

import pytest

from shijiajing_agent.contracts import Offer, SellerType
from shijiajing_agent.domain.taxonomy import Taxonomy, TaxonomyFile, load_taxonomy


@pytest.fixture(scope="session")
def taxonomy() -> Taxonomy:
    return load_taxonomy()


def offer(
    offer_id: str,
    *,
    platform: str = "taobao",
    category_id: str = "headphone",
    brand: str = "Sony",
    model: str = "WH-1000XM5",
    price: float | None = 1999.0,
    title: str = "Sony 索尼 WH-1000XM5 头戴式降噪耳机",
    identity: dict[str, str] | None = None,
    variant: dict[str, str] | None = None,
    same_item_key: str | None = None,
    seller_type: SellerType = SellerType.THIRD_PARTY,
    rating: float | None = None,
    sales: float | None = None,
    source_updated_at: str | None = None,
    coupon: float | None = None,
    shipping: float | None = None,
    shop_id: str = "shop1",
    source_product_id: str | None = None,
) -> Offer:
    return Offer(
        offer_id=offer_id,
        platform=platform,
        source_product_id=source_product_id or f"sp-{offer_id}",
        shop_id=shop_id,
        source_updated_at=source_updated_at or "2026-08-01T00:00:00Z",
        title=title,
        category_id=category_id,
        brand=brand,
        model=model,
        same_item_key=same_item_key,
        identity_attributes=dict(identity or {"connectivity": "蓝牙", "wearing_style": "头戴式"}),
        variant_attributes=dict(variant or {"color": "黑色", "set_type": "单件"}),
        price=price,
        coupon_amount=coupon,
        shipping_fee=shipping,
        seller_type=seller_type,
        rating=rating,
        sales=sales,
    )


@pytest.fixture
def sample_offer() -> Offer:
    return offer("o1")


@pytest.fixture
def taxonomy_file_data() -> dict:
    return {
        "schema_version": "1.0",
        "taxonomy_version": "test.1",
        "categories": [
            {
                "category_id": "headphone",
                "category_name": "耳机",
                "aliases": ["耳机", "蓝牙耳机"],
                "brand_aliases": {"索尼": "Sony"},
                "model_normalization_rules": {"uppercase": True},
                "searchable_attributes": ["noise_cancellation"],
                "identity_attributes": ["connectivity", "wearing_style"],
                "variant_attributes": ["color", "set_type"],
                "attribute_schema": {
                    "noise_cancellation": {"type": "string", "enum": ["主动降噪", "被动降噪"]},
                    "connectivity": {"type": "string", "enum": ["蓝牙", "有线"]},
                    "color": {"type": "string"},
                },
            }
        ],
        "unit_rules": [],
        "common_brand_aliases": {"索尼": "Sony"},
    }


@pytest.fixture
def mini_taxonomy(taxonomy_file_data: dict) -> Taxonomy:
    return Taxonomy(TaxonomyFile.model_validate(taxonomy_file_data))
