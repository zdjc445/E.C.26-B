"""召回融合策略测试。"""

from __future__ import annotations

import pytest

from shijiajing_agent.contracts import RetrievalCandidate
from shijiajing_agent.domain.retrieval_fusion import WeightedScoreFusion
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
