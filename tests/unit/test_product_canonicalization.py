"""LLM 商品归一化补丁、证据校验、降级与同款聚类。"""

from __future__ import annotations

from shijiajing_agent.adapters.cache import InMemoryVersionedCache
from shijiajing_agent.contracts import (
    CanonicalFieldEvidence,
    Offer,
    ProductCanonicalizationBatch,
    ProductCanonicalizationItem,
)
from shijiajing_agent.domain.product_canonicalization import canonicalize_offers
from shijiajing_agent.domain.same_item import default_same_item_matcher


class FakeCanonicalizer:
    version = "fake-v1"

    def __init__(self, result: ProductCanonicalizationBatch | Exception) -> None:
        self.result = result
        self.calls = 0

    async def canonicalize(self, offers, taxonomy):
        del offers, taxonomy
        self.calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def _cross_platform_offers() -> list[Offer]:
    return [
        Offer(
            offer_id="cn",
            platform="taobao",
            title="索尼 WH-1000XM5 黑色无线降噪耳机",
            price=1999,
        ),
        Offer(
            offer_id="en",
            platform="jd",
            title="Sony WH 1000XM5 Black Wireless Noise Cancelling Headphones",
            price=2099,
        ),
    ]


def _proposal(
    offer_id: str,
    *,
    category_evidence: str,
    brand_evidence: str,
    model_evidence: str,
    connectivity_evidence: str,
    color_evidence: str,
) -> ProductCanonicalizationItem:
    return ProductCanonicalizationItem(
        offer_id=offer_id,
        category_id="headphone",
        brand="Sony",
        model="WH-1000XM5",
        identity_attributes={"connectivity": "蓝牙"},
        variant_attributes={"color": "黑色"},
        evidence=[
            CanonicalFieldEvidence(
                field_path="category_id", raw_value=category_evidence, confidence=0.99
            ),
            CanonicalFieldEvidence(field_path="brand", raw_value=brand_evidence, confidence=0.99),
            CanonicalFieldEvidence(field_path="model", raw_value=model_evidence, confidence=0.99),
            CanonicalFieldEvidence(
                field_path="identity_attributes.connectivity",
                raw_value=connectivity_evidence,
                confidence=0.9,
            ),
            CanonicalFieldEvidence(
                field_path="variant_attributes.color",
                raw_value=color_evidence,
                confidence=0.9,
            ),
        ],
    )


async def test_llm_fields_are_validated_then_used_for_matching(taxonomy) -> None:
    canonicalizer = FakeCanonicalizer(
        ProductCanonicalizationBatch(
            items=[
                _proposal(
                    "cn",
                    category_evidence="耳机",
                    brand_evidence="索尼",
                    model_evidence="WH-1000XM5",
                    connectivity_evidence="无线",
                    color_evidence="黑色",
                ),
                _proposal(
                    "en",
                    category_evidence="Headphones",
                    brand_evidence="Sony",
                    model_evidence="WH 1000XM5",
                    connectivity_evidence="Wireless",
                    color_evidence="Black",
                ),
            ]
        )
    )

    run = await canonicalize_offers(_cross_platform_offers(), taxonomy, canonicalizer)

    assert canonicalizer.calls == 1
    assert run.rejected_fields == 0
    assert [item.normalized_brand for item in run.candidates] == ["Sony", "Sony"]
    assert [item.normalized_model for item in run.candidates] == ["WH 1000XM5"] * 2
    assert run.candidates[0].offer.normalized_title == run.candidates[1].offer.normalized_title
    matcher = default_same_item_matcher(taxonomy)
    pairs = matcher.generate_candidates(run.candidates)
    assert pairs == [(0, 1)]
    assert matcher.cluster(run.candidates, pairs) == [[0, 1]]


async def test_structured_source_field_wins_over_conflicting_model_value(taxonomy) -> None:
    offer = Offer(
        offer_id="source",
        platform="jd",
        title="Sony WH-1000XM5 耳机",
        category_id="headphone",
        brand="Sony",
        model="WH-1000XM5",
    )
    canonicalizer = FakeCanonicalizer(
        ProductCanonicalizationBatch(
            items=[
                ProductCanonicalizationItem(
                    offer_id="source",
                    brand="Bose",
                    evidence=[
                        CanonicalFieldEvidence(
                            field_path="brand", raw_value="Sony", confidence=0.99
                        )
                    ],
                )
            ]
        )
    )

    run = await canonicalize_offers([offer], taxonomy, canonicalizer)

    assert run.candidates[0].normalized_brand == "Sony"
    assert run.rejected_fields == 1
    assert "canonicalization_conflict:brand" in run.candidates[0].normalization_failures


async def test_missing_evidence_is_rejected(taxonomy) -> None:
    offer = Offer(offer_id="missing", platform="jd", title="未知品牌耳机")
    canonicalizer = FakeCanonicalizer(
        ProductCanonicalizationBatch(
            items=[ProductCanonicalizationItem(offer_id="missing", brand="Sony")]
        )
    )

    run = await canonicalize_offers([offer], taxonomy, canonicalizer)

    assert run.candidates[0].normalized_brand is None
    assert run.rejected_fields == 1


async def test_model_failure_falls_back_to_rule_normalization(taxonomy) -> None:
    offer = Offer(
        offer_id="fallback",
        platform="jd",
        title="索尼 WH-1000XM5 耳机",
        category_id="headphone",
        brand="索尼",
        model="wh-1000xm5",
    )
    canonicalizer = FakeCanonicalizer(RuntimeError("model unavailable"))

    run = await canonicalize_offers([offer], taxonomy, canonicalizer)

    assert run.fallback_batches == 1
    assert run.candidates[0].normalized_brand == "Sony"
    assert run.candidates[0].normalized_model == "WH 1000XM5"


async def test_versioned_cache_avoids_repeated_model_call(taxonomy) -> None:
    offer = _cross_platform_offers()[0]
    canonicalizer = FakeCanonicalizer(
        ProductCanonicalizationBatch(
            items=[
                _proposal(
                    "cn",
                    category_evidence="耳机",
                    brand_evidence="索尼",
                    model_evidence="WH-1000XM5",
                    connectivity_evidence="无线",
                    color_evidence="黑色",
                )
            ]
        )
    )
    cache = InMemoryVersionedCache()

    first = await canonicalize_offers([offer], taxonomy, canonicalizer, cache=cache)
    second = await canonicalize_offers([offer], taxonomy, canonicalizer, cache=cache)

    assert first.model_calls == 1
    assert second.cache_hits == 1
    assert canonicalizer.calls == 1
