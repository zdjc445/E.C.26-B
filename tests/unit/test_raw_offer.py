"""原始 SKU/Offer 契约和单一索引文本测试。"""

from __future__ import annotations

import json
import os

from shijiajing_agent.contracts import Offer
from shijiajing_agent.domain.raw_offer import (
    Availability,
    PriceBasis,
    Provenance,
    RawAttribute,
    RawAttributeScope,
    RecordKind,
    build_offer_id,
    build_raw_search_text,
    prepare_raw_offer,
    raw_offer_from_mapping,
    source_content_hash,
)


def test_offer_preserves_raw_sku_scope_and_price_semantics() -> None:
    offer = raw_offer_from_mapping(
        {
            "platform": "platform_b",
            "source_product_id": "item_21",
            "source_sku_id": "sku_8",
            "source_offer_id": "listing_7",
            "shop_id": "shop_7",
            "title": "K87 mechanical keyboard",
            "raw_category_path": "Computers / Keyboards",
            "raw_attributes": [
                {
                    "attribute_id": "a2",
                    "raw_key": "color",
                    "raw_value": "white",
                    "scope": "sku",
                    "source_locator": "/skus/8/options/color",
                },
                {
                    "attribute_id": "a1",
                    "raw_key": "switch",
                    "raw_value": "red",
                    "scope": "sku",
                    "source_locator": "/skus/8/options/switch",
                },
            ],
            "record_kind": "sku_offer",
            "provenance": "source_native",
            "availability": "available",
            "price_basis": "sku_listed",
            "price": 199,
        }
    )

    assert offer.offer_id.startswith("platform_b:offer:")
    assert offer.record_kind is RecordKind.SKU_OFFER
    assert offer.provenance is Provenance.SOURCE_NATIVE
    assert offer.availability is Availability.AVAILABLE
    assert offer.price_basis is PriceBasis.SKU_LISTED
    assert [item.attribute_id for item in offer.raw_attributes] == ["a2", "a1"]
    assert offer.source_content_hash and len(offer.source_content_hash) == 64
    assert offer.search_text_hash and len(offer.search_text_hash) == 64


def test_raw_search_text_is_deterministic_and_utf8_safe() -> None:
    raw = [
        RawAttribute(
            attribute_id="b",
            raw_key="color",
            raw_value="白",
            scope=RawAttributeScope.SKU,
        ),
        RawAttribute(
            attribute_id="a",
            raw_key="switch",
            raw_value="红轴",
            scope=RawAttributeScope.SKU,
        ),
    ]
    offer = Offer(
        offer_id="o1",
        platform="p",
        title="键盘",
        raw_category_path="键盘",
        raw_attributes=raw,
        identity_attributes={},
        variant_attributes={},
        descriptive_attributes={},
    )
    text = build_raw_search_text(offer)
    assert text.index("sku.switch") < text.index("sku.color")
    assert text.startswith("title: 键盘\ncategory: 键盘")
    assert len(text.encode("utf-8")) <= 16 * 1024

    huge = offer.model_copy(update={"title": "字" * 20_000})
    truncated = build_raw_search_text(huge)
    assert len(truncated.encode("utf-8")) <= 16 * 1024
    truncated.encode("utf-8").decode("utf-8")


def test_source_hash_excludes_derived_search_text() -> None:
    offer = Offer(offer_id="o1", platform="p", source_product_id="item")
    prepared = prepare_raw_offer(offer)
    assert source_content_hash(offer) == source_content_hash(prepared)
    assert prepared.search_text_hash is not None


def test_offer_id_uses_structured_identity_without_delimiter_collisions() -> None:
    first = build_offer_id(platform="p", source_product_id="ab", source_sku_id="c")
    second = build_offer_id(platform="p", source_product_id="a", source_sku_id="bc")
    assert first != second


def test_index_dry_run_writes_manifest_without_taxonomy_or_external_config(
    tmp_path, monkeypatch, capsys
) -> None:
    snapshot = tmp_path / "source.jsonl"
    snapshot.write_text(
        "\n".join(
            json.dumps(item, ensure_ascii=False)
            for item in (
                {
                    "platform": "p",
                    "source_product_id": "item",
                    "source_sku_id": "sku-1",
                    "title": "红轴键盘",
                    "raw_category_path": "键盘",
                    "raw_attributes": [
                        {
                            "attribute_id": "a1",
                            "raw_key": "switch",
                            "raw_value": "red",
                            "scope": "sku",
                        }
                    ],
                },
                {
                    "offer_id": "summary-1",
                    "platform": "p",
                    "source_product_id": "item-summary",
                    "record_kind": "product_summary",
                    "title": "键盘（多规格）",
                },
            )
        )
        + "\n",
        encoding="utf-8",
    )
    for key in list(os.environ):
        if key.startswith("SHIJIAJING_"):
            monkeypatch.delenv(key, raising=False)

    from shijiajing_agent.tools.index_products import main

    manifest = tmp_path / "manifest.json"
    assert main([str(snapshot), "--dry-run", "--manifest", str(manifest)]) == 0
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["valid_offer_count"] == 1
    assert payload["embedding_model"] is None
    assert "product_summary：1 行" in capsys.readouterr().out
