"""动态商品 Schema 阶段 1 的纯领域行为。"""

from __future__ import annotations

import pytest

from shijiajing_agent.adapters.cache import InMemoryVersionedCache
from shijiajing_agent.contracts import (
    DynamicAttributeProposal,
    DynamicCanonicalField,
    DynamicCanonicalizationBatch,
    DynamicCanonicalizationItem,
    DynamicConceptProposal,
    DynamicSchemaProposal,
    EvidenceSpan,
    Offer,
    OfferConceptAssignment,
    VerifiedDynamicSchema,
)
from shijiajing_agent.domain.dynamic_schema import (
    DynamicSchemaValidationError,
    verify_dynamic_schema,
)
from shijiajing_agent.domain.open_world_normalization import (
    GenericNormalizer,
    apply_dynamic_patch,
)
from shijiajing_agent.domain.product_canonicalization import (
    canonicalize_offers,
    dynamic_canonicalize_offers,
)
from shijiajing_agent.domain.taxonomy import Taxonomy


def _offer(offer_id: str, title: str) -> Offer:
    return Offer(offer_id=offer_id, platform="test", title=title)


def _evidence(offer_id: str, raw_value: str) -> EvidenceSpan:
    return EvidenceSpan(offer_id=offer_id, source_path="title", raw_value=raw_value)


def _schema_proposal(offers: list[Offer]) -> DynamicSchemaProposal:
    return DynamicSchemaProposal(
        concepts=[
            DynamicConceptProposal(
                local_concept_id="widget",
                canonical_label="Widget",
                label_confidence=0.99,
                evidence=[_evidence(item.offer_id, "Widget") for item in offers],
                attributes=[
                    DynamicAttributeProposal(
                        canonical_key="color",
                        aliases=["颜色"],
                        role="variant",
                        value_kind="string",
                        role_confidence=0.99,
                        evidence=[
                            _evidence(offers[0].offer_id, "red"),
                            _evidence(offers[1].offer_id, "blue"),
                        ],
                    )
                ],
            )
        ],
        assignments=[
            OfferConceptAssignment(
                offer_id=item.offer_id,
                local_concept_id="widget",
                confidence=0.99,
                evidence=[_evidence(item.offer_id, "Widget")],
            )
            for item in offers
        ],
    )


def test_dynamic_schema_hashes_verified_content_and_demotes_weak_roles() -> None:
    offers = [_offer("a", "Acme Widget red"), _offer("b", "Acme Widget blue")]
    proposal = _schema_proposal(offers)
    schema = verify_dynamic_schema(proposal, offers)

    assert len(schema.schema_id) == 64
    assert schema.variant_keys_for_offer("a") == ["color"]

    weak = proposal.model_copy(
        update={
            "concepts": [
                proposal.concepts[0].model_copy(
                    update={
                        "attributes": [
                            proposal.concepts[0]
                            .attributes[0]
                            .model_copy(update={"role": "identity", "role_confidence": 0.5})
                        ]
                    }
                )
            ]
        }
    )
    weak_schema = verify_dynamic_schema(weak, offers)
    assert weak_schema.concepts[0].attributes[0].role == "descriptive"


def test_dynamic_schema_rejects_duplicate_assignment_and_forged_evidence() -> None:
    offers = [_offer("a", "Acme Widget red"), _offer("b", "Acme Widget blue")]
    proposal = _schema_proposal(offers).model_copy(
        update={
            "assignments": [
                *_schema_proposal(offers).assignments,
                OfferConceptAssignment(
                    offer_id="a",
                    local_concept_id="widget",
                    confidence=0.99,
                    evidence=[_evidence("a", "Widget")],
                ),
            ]
        }
    )
    with pytest.raises(DynamicSchemaValidationError):
        verify_dynamic_schema(proposal, offers)

    forged = _schema_proposal(offers).model_copy(
        update={
            "concepts": [
                _schema_proposal(offers)
                .concepts[0]
                .model_copy(update={"evidence": [_evidence("a", "not-in-title")]})
            ]
        }
    )
    schema = verify_dynamic_schema(forged, offers)
    assert schema.assignments == []
    assert schema.concepts == []


def test_dynamic_patch_keeps_evidence_grounded_and_marks_role_conflict_descriptive() -> None:
    offer = _offer("a", "Acme Widget red")
    offers = [offer, _offer("b", "Acme Widget blue")]
    schema = verify_dynamic_schema(_schema_proposal(offers), offers)
    item = DynamicCanonicalizationItem(
        offer_id="a",
        local_concept_id="widget",
        category_concept="Widget",
        category_confidence=0.99,
        category_evidence=_evidence("a", "Widget"),
        brand="Acme",
        brand_confidence=0.99,
        brand_evidence=_evidence("a", "Acme"),
        fields=[
            DynamicCanonicalField(
                canonical_key="color",
                canonical_value="red",
                role="identity",
                confidence=0.99,
                evidence=_evidence("a", "red"),
            )
        ],
    )
    result = apply_dynamic_patch(GenericNormalizer().normalize_offer(offer), item, schema, offer)

    assert result.candidate.normalized_category_concept == "Widget"
    assert result.candidate.normalized_descriptive == {"color": "red"}
    assert result.candidate.normalized_variant == {}
    assert result.descriptive_only_count == 1


class _SchemaInducer:
    version = "test-schema"

    async def induce_schema(self, offers: list[Offer]) -> DynamicSchemaProposal:
        return _schema_proposal(offers)


class _BrokenCanonicalizer:
    version = "broken"

    async def canonicalize_dynamic(
        self, offers: list[Offer], schema: VerifiedDynamicSchema
    ) -> DynamicCanonicalizationBatch:
        del offers, schema
        raise RuntimeError("offline")


class _Canonicalizer:
    version = "test-canonicalizer"

    def __init__(self) -> None:
        self.calls = 0

    async def canonicalize_dynamic(
        self, offers: list[Offer], schema: VerifiedDynamicSchema
    ) -> DynamicCanonicalizationBatch:
        self.calls += 1
        return DynamicCanonicalizationBatch(
            schema_id=schema.schema_id,
            items=[
                DynamicCanonicalizationItem(
                    offer_id=offer.offer_id,
                    local_concept_id="widget",
                    category_concept="Widget",
                    category_confidence=0.99,
                    category_evidence=_evidence(offer.offer_id, "Widget"),
                )
                for offer in offers
            ],
        )


class _VariantCanonicalizer(_Canonicalizer):
    async def canonicalize_dynamic(
        self, offers: list[Offer], schema: VerifiedDynamicSchema
    ) -> DynamicCanonicalizationBatch:
        self.calls += 1
        return DynamicCanonicalizationBatch(
            schema_id=schema.schema_id,
            items=[
                DynamicCanonicalizationItem(
                    offer_id=offer.offer_id,
                    local_concept_id="widget",
                    category_concept="Widget",
                    category_confidence=0.99,
                    category_evidence=_evidence(offer.offer_id, "Widget"),
                    fields=[
                        DynamicCanonicalField(
                            canonical_key="color",
                            canonical_value=("red" if "red" in offer.title else "blue"),
                            role="variant",
                            confidence=0.99,
                            evidence=_evidence(
                                offer.offer_id,
                                "red" if "red" in offer.title else "blue",
                            ),
                        )
                    ],
                )
                for offer in offers
            ],
        )


async def test_dynamic_batch_failure_returns_generic_candidates() -> None:
    offers = [
        _offer("a", "Acme Widget red").model_copy(update={"brand": "Acme"}),
        _offer("b", "Acme Widget blue").model_copy(update={"brand": "Acme"}),
    ]
    run = await dynamic_canonicalize_offers(offers, _SchemaInducer(), _BrokenCanonicalizer())

    assert run.fallback_batches == 1
    assert run.candidates[0].normalized_category_concept is None
    assert run.candidates[0].normalized_brand == "Acme"


async def test_dynamic_schema_and_exact_results_are_cached() -> None:
    offers = [_offer("a", "Acme Widget red"), _offer("b", "Acme Widget blue")]
    canonicalizer = _Canonicalizer()
    cache = InMemoryVersionedCache()

    first = await dynamic_canonicalize_offers(offers, _SchemaInducer(), canonicalizer, cache=cache)
    second = await dynamic_canonicalize_offers(offers, _SchemaInducer(), canonicalizer, cache=cache)

    assert first.model_calls == 2
    assert second.cache_hits == 2
    assert canonicalizer.calls == 1


async def test_dynamic_shadow_keeps_static_output_and_records_field_diffs(
    taxonomy: Taxonomy,
) -> None:
    offers = [_offer("a", "Acme Widget red"), _offer("b", "Acme Widget blue")]

    run = await canonicalize_offers(
        offers,
        taxonomy,
        canonicalizer=None,
        mode="dynamic_shadow",
        dynamic_schema_inducer=_SchemaInducer(),
        dynamic_product_canonicalizer=_Canonicalizer(),
    )

    assert all(candidate.normalized_category_id is None for candidate in run.candidates)
    assert all(
        candidate.normalized_category_concept == "Widget"
        for candidate in run.shadow_candidates or []
    )
    assert run.schema_id is not None
    assert run.shadow_summary is not None
    assert run.shadow_summary["changed_candidate_count"] == 2
    assert run.shadow_summary["category_fill_count"] == 2
    assert run.shadow_summary["field_difference_count"] == 2


async def test_hybrid_preserves_taxonomy_fields_and_fills_dynamic_variant(
    taxonomy: Taxonomy,
) -> None:
    offers = [
        _offer("a", "Sony Widget red").model_copy(
            update={"category_id": "headphone", "brand": "Sony", "variant_attributes": {}}
        ),
        _offer("b", "Sony Widget blue").model_copy(
            update={"category_id": "headphone", "brand": "Sony", "variant_attributes": {}}
        ),
    ]

    run = await canonicalize_offers(
        offers,
        taxonomy,
        canonicalizer=None,
        mode="hybrid",
        dynamic_schema_inducer=_SchemaInducer(),
        dynamic_product_canonicalizer=_VariantCanonicalizer(),
    )

    assert [candidate.normalized_category_id for candidate in run.candidates] == [
        "headphone",
        "headphone",
    ]
    assert all(candidate.normalized_category_concept is None for candidate in run.candidates)
    assert all(candidate.normalized_brand == "Sony" for candidate in run.candidates)
    assert run.candidates[0].normalized_variant == {"color": "red"}
    assert run.candidates[1].normalized_variant == {"color": "blue"}
