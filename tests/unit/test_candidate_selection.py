"""评估窗口的有界、多样性选择测试。"""

from __future__ import annotations

from shijiajing_agent.contracts import RetrievalCandidate
from shijiajing_agent.domain.candidate_selection import select_candidate_window
from tests.unit.conftest import offer


def test_window_round_robins_listing_buckets_before_filling_scores() -> None:
    crowded = [
        RetrievalCandidate(
            offer=offer(
                f"crowded-{index}",
                source_product_id="product-a",
                shop_id="shop-a",
            ),
            recall_score=1.0 - index / 100,
        )
        for index in range(4)
    ]
    other = RetrievalCandidate(
        offer=offer(
            "other-0",
            source_product_id="product-b",
            shop_id="shop-b",
        ),
        recall_score=0.5,
    )

    result = select_candidate_window([*crowded, other], limit=3)

    assert [item.offer.offer_id for item in result.candidates] == [
        "crowded-0",
        "other-0",
        "crowded-1",
    ]
    assert result.truncated_count == 2


def test_window_does_not_group_missing_product_ids() -> None:
    candidates = [
        RetrievalCandidate(
            offer=offer(f"missing-{index}").model_copy(update={"source_product_id": None}),
            recall_score=1.0 - index / 10,
        )
        for index in range(3)
    ]

    result = select_candidate_window(candidates, limit=2)

    assert len(result.candidates) == 2
    assert result.truncated_count == 1
