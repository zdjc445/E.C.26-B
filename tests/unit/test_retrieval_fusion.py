"""召回融合策略测试。"""

from __future__ import annotations

import pytest

from shijiajing_agent.contracts import RetrievalCandidate
from shijiajing_agent.domain.retrieval_fusion import BestQueryChannelRRF, WeightedScoreFusion
from tests.unit.conftest import offer


def candidate(
    offer_id: str,
    *,
    dense: float | None,
    sparse: float | None,
    metadata: float,
    image: float | None = None,
) -> RetrievalCandidate:
    return RetrievalCandidate(
        offer=offer(offer_id),
        dense_text_score=dense,
        sparse_score=sparse,
        metadata_match=metadata,
        image_similarity=image,
    )


def test_weighted_fusion_matches_text_baseline_and_is_deterministic() -> None:
    result = WeightedScoreFusion().fuse(
        {
            "dense": [candidate("o-dense", dense=1.0, sparse=None, metadata=0.0)],
            "sparse": [candidate("o-sparse", dense=None, sparse=1.0, metadata=1.0)],
            "both": [candidate("o-both", dense=0.0, sparse=0.0, metadata=0.0)],
        },
        limit=10,
    )

    by_id = {item.offer.offer_id: item for item in result}
    assert by_id["o-dense"].recall_score == pytest.approx(0.50 / 0.70)
    assert by_id["o-sparse"].recall_score == pytest.approx(1.0)
    assert by_id["o-both"].recall_score == pytest.approx(0.0)
    assert [item.offer.offer_id for item in result] == ["o-sparse", "o-dense", "o-both"]


def test_weighted_fusion_uses_image_weights_when_image_channel_exists() -> None:
    result = WeightedScoreFusion().fuse(
        {"all": [candidate("o1", dense=1.0, sparse=None, metadata=1.0, image=1.0)]},
        limit=1,
    )

    assert result[0].recall_score == pytest.approx(1.0)


def test_best_query_channel_rrf_deduplicates_aliases_and_uses_best_rank() -> None:
    first = candidate("o1", dense=0.9, sparse=None, metadata=0.0).model_copy(
        update={"query_ids": ["q1"]}
    )
    second = candidate("o2", dense=0.8, sparse=None, metadata=0.0).model_copy(
        update={"query_ids": ["q1"]}
    )
    result = BestQueryChannelRRF().fuse(
        {
            "q1": {"dense": [first, second, first]},
            "q2": {"dense": [second, first]},
        },
        limit=10,
        usable_channels=["dense"],
    )

    assert [item.offer.offer_id for item in result] == ["o1", "o2"]
    assert result[0].recall_score == pytest.approx(1 / 61)
    assert result[0].query_ids == ["q1"]


def test_best_query_channel_rrf_weights_empty_success_but_excludes_failure() -> None:
    item = candidate("o1", dense=0.9, sparse=None, metadata=0.0)
    two_channels = BestQueryChannelRRF().fuse(
        {"q1": {"dense": [item]}},
        limit=10,
        usable_channels=["dense", "sparse"],
    )
    one_channel = BestQueryChannelRRF().fuse(
        {"q1": {"dense": [item]}},
        limit=10,
        usable_channels=["dense"],
    )

    assert two_channels[0].recall_score == pytest.approx(1 / (2 * 61))
    assert one_channel[0].recall_score == pytest.approx(1 / 61)


def test_best_query_channel_rrf_tie_breaks_by_offer_id() -> None:
    result = BestQueryChannelRRF().fuse(
        {
            "q1": {"dense": [candidate("b", dense=1.0, sparse=None, metadata=0.0)]},
            "q2": {"dense": [candidate("a", dense=1.0, sparse=None, metadata=0.0)]},
        },
        limit=10,
        usable_channels=["dense"],
    )

    assert [item.offer.offer_id for item in result] == ["a", "b"]
