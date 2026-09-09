"""检索后硬要求的三态资格校验测试。"""

from __future__ import annotations

from shijiajing_agent.contracts import (
    ConstraintSource,
    NormalizedCandidate,
    Offer,
    RawAttribute,
    RetrievalCandidate,
    ShoppingConstraints,
    SourcedValue,
)
from shijiajing_agent.domain.open_world_normalization import GenericNormalizer
from shijiajing_agent.domain.requirements import (
    build_semantic_requirements,
    qualify_candidate,
)
from shijiajing_agent.rag_contracts import RequirementState, SemanticRequirement
from shijiajing_agent.services.comparison import ComparisonService
from tests.unit.conftest import offer


def _candidate(*, raw_key: str | None = None, raw_value: str | None = None) -> NormalizedCandidate:
    raw_attributes = []
    if raw_key is not None and raw_value is not None:
        raw_attributes.append(
            RawAttribute(
                attribute_id="attr-1",
                raw_key=raw_key,
                raw_value=raw_value,
                scope="sku",
            )
        )
    item = Offer(
        offer_id="offer-1",
        platform="jd",
        category_id="keyboard",
        title="mechanical keyboard red",
        raw_attributes=raw_attributes,
        identity_attributes={},
        variant_attributes={},
    )
    return GenericNormalizer().normalize_offer(item)


def _requirements(value: object) -> list[SemanticRequirement]:
    return build_semantic_requirements(
        ShoppingConstraints(
            category_id=SourcedValue(value="keyboard", source=ConstraintSource.USER_TEXT),
            attributes=SourcedValue(value={"switch": value}, source=ConstraintSource.USER_TEXT),
        )
    )


def test_raw_sku_switch_red_satisfies_requirement() -> None:
    result = qualify_candidate(_candidate(raw_key="switch", raw_value="red"), _requirements("red"))

    switch = next(item for item in result.matches if item.requirement_id.endswith(":switch"))
    assert result.eligible is True
    assert switch.state is RequirementState.SATISFIED
    assert switch.evidence_refs == ["raw_attributes.attr-1.raw_value"]


def test_case_color_red_does_not_satisfy_switch_requirement() -> None:
    result = qualify_candidate(
        _candidate(raw_key="case_color", raw_value="red"), _requirements("red")
    )

    switch = next(item for item in result.matches if item.requirement_id.endswith(":switch"))
    assert result.eligible is False
    assert switch.state is RequirementState.UNKNOWN


def test_blue_switch_conflicts_and_generic_red_does_not_prove_cherry_mx() -> None:
    blue = qualify_candidate(_candidate(raw_key="switch", raw_value="blue"), _requirements("red"))
    precise = qualify_candidate(
        _candidate(raw_key="switch", raw_value="red"), _requirements("Cherry MX Red")
    )

    assert blue.matches[-1].state is RequirementState.CONFLICT
    assert precise.matches[-1].state is RequirementState.UNKNOWN


async def test_comparison_does_not_rank_conflicting_skus(mini_taxonomy: object) -> None:
    def with_switch(offer_id: str, switch: str) -> RetrievalCandidate:
        item = offer(offer_id).model_copy(
            update={
                "raw_attributes": [
                    RawAttribute(
                        attribute_id=f"attr-{offer_id}",
                        raw_key="switch",
                        raw_value=switch,
                        scope="sku",
                    )
                ]
            }
        )
        return RetrievalCandidate(offer=item, recall_score=0.8)

    constraints = ShoppingConstraints(
        category_id=SourcedValue(value="headphone", source=ConstraintSource.USER_TEXT),
        attributes=SourcedValue(value={"switch": "red"}, source=ConstraintSource.USER_TEXT),
    )
    result = await ComparisonService(mini_taxonomy).compare_candidates(
        [with_switch("red", "red"), with_switch("blue", "blue")], constraints
    )

    assert result.excluded_offer_ids == ["blue"]
    assert all(
        item.offer_id != "blue" for group in result.ranked_groups for item in group.group.offers
    )
