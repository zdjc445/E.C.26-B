"""二期工程不变量评测数据集契约测试。"""

from __future__ import annotations

from shijiajing_agent.contracts import Offer, RetrievalCandidate
from shijiajing_agent.eval_engineering import retrieval_strategy_sample_from_result
from shijiajing_agent.evals import default_datasets_dir, load_all_datasets
from shijiajing_agent.ports.retrieval import RetrievalResult


def test_engineering_datasets_are_loaded_with_strict_models() -> None:
    datasets = load_all_datasets(default_datasets_dir())

    assert set(datasets) == {
        "recognition",
        "intent",
        "retrieval",
        "same_item",
        "ranking",
        "workflow",
        "memory",
        "multi_agent",
        "interrupt",
        "cache",
        "retrieval_strategy",
    }
    assert len(datasets["memory"]) == 2
    assert len(datasets["multi_agent"]) == 2
    assert len(datasets["interrupt"]) == 4
    assert len(datasets["cache"]) == 2
    assert len(datasets["retrieval_strategy"]) == 2


def test_retrieval_strategy_sample_from_result_preserves_real_channel_order() -> None:
    first = RetrievalCandidate(
        offer=Offer(offer_id="offer-1", platform="jd", title="first"),
        dense_text_score=0.9,
        sparse_score=0.2,
        channel_sources=["dense", "sparse"],
    )
    second = RetrievalCandidate(
        offer=Offer(offer_id="offer-2", platform="jd", title="second"),
        dense_text_score=0.4,
        sparse_score=0.8,
        channel_sources=["dense", "sparse"],
    )
    sample = retrieval_strategy_sample_from_result(
        "strategy-live-1",
        {"query_text": "first", "hard_filters": {"category_id": "headphone"}},
        RetrievalResult(candidates=[first, second], total_found=2),
        expected_spu_ids=["spu-1"],
        expected_sku_ids=["sku-1"],
        expected_top_sku_ids=["sku-1"],
        gold_spu_by_offer_id={"offer-1": "spu-1", "offer-2": "spu-2"},
        gold_sku_by_offer_id={"offer-1": "sku-1", "offer-2": "sku-2"},
    )

    assert sample.channel_orders == {
        "dense": ["offer-1", "offer-2"],
        "sparse": ["offer-2", "offer-1"],
    }
    assert sample.expected_sku_ids == ["sku-1"]
    assert sample.gold_sku_by_offer_id["offer-1"] == "sku-1"
