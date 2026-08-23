"""工程不变量夹具实际执行器测试。"""

from __future__ import annotations

import pytest

from shijiajing_agent.contracts import Offer, RetrievalCandidate
from shijiajing_agent.domain.taxonomy import load_taxonomy
from shijiajing_agent.engineering_eval import evaluate_engineering_datasets
from shijiajing_agent.eval_data import EvalSampleMeta
from shijiajing_agent.eval_engineering import (
    RetrievalStrategySample,
    evaluate_retrieval_strategies,
)
from shijiajing_agent.evals import default_datasets_dir, load_all_datasets


@pytest.mark.asyncio
async def test_engineering_fixture_executor_passes_seed_data() -> None:
    report = await evaluate_engineering_datasets(
        load_all_datasets(default_datasets_dir()),
        load_taxonomy(),
    )

    assert report.all_passed is True
    assert {check.kind for check in report.checks} == {
        "memory",
        "multi_agent",
        "interrupt",
        "cache",
    }
    assert all(not check.failed_ids for check in report.checks)
    assert report.invariant_gate_passed is True
    assert {invariant.name for invariant in report.invariants} == {
        "user_hard_filter_violation_count",
        "cross_user_memory_leakage_count",
        "replay_duplicate_side_effect_count",
        "wrong_sku_group_count",
        "price_fact_error_count",
        "sensitive_field_leakage_count",
    }
    assert all(invariant.sample_count > 0 for invariant in report.invariants)
    assert all(invariant.violation_count == 0 for invariant in report.invariants)


def test_retrieval_strategy_comparison_runs_all_three_production_strategies() -> None:
    samples = [
        RetrievalStrategySample.model_validate(row)
        for row in load_all_datasets(default_datasets_dir())["retrieval_strategy"]
    ]
    report = evaluate_retrieval_strategies(samples)

    assert [result.strategy for result in report.results] == [
        "weighted",
        "rrf",
        "weighted_rerank",
    ]
    assert report.recommended_strategy == "weighted"
    assert all(result.hard_filter_violation_count == 0 for result in report.results)
    assert all(result.sku_recall_at_20 == 1.0 for result in report.results)


def test_retrieval_strategy_comparison_uses_external_gold_mapping() -> None:
    sample = RetrievalStrategySample(
        id="strategy-gold-map",
        query={"query_text": "Sony headphone", "hard_filters": {"category_id": "headphone"}},
        candidates=[
            RetrievalCandidate(
                offer=Offer(
                    offer_id="offer-source-1",
                    platform="jd",
                    title="Sony headphone",
                    category_id="headphone",
                    same_item_key="source-spu-1",
                    sku_key="source-sku-1",
                ),
                dense_text_score=0.9,
                sparse_score=0.8,
                metadata_match=1.0,
                channel_sources=["dense", "sparse"],
            )
        ],
        channel_orders={"dense": ["offer-source-1"]},
        expected_spu_ids=["gold-spu-1"],
        expected_sku_ids=["gold-sku-1"],
        expected_top_sku_ids=["gold-sku-1"],
        gold_spu_by_offer_id={"offer-source-1": "gold-spu-1"},
        gold_sku_by_offer_id={"offer-source-1": "gold-sku-1"},
    )

    report = evaluate_retrieval_strategies([sample])

    assert all(result.spu_recall_at_20 == 1.0 for result in report.results)
    assert all(result.sku_recall_at_20 == 1.0 for result in report.results)


def test_retrieval_strategy_comparison_rejects_incomplete_gold_mapping() -> None:
    sample = RetrievalStrategySample(
        id="strategy-incomplete-gold-map",
        query={"query_text": "Sony headphone", "hard_filters": {"category_id": "headphone"}},
        candidates=[
            RetrievalCandidate(
                offer=Offer(
                    offer_id="offer-source-1",
                    platform="jd",
                    title="Sony headphone",
                    category_id="headphone",
                    same_item_key="source-spu-1",
                    sku_key="source-sku-1",
                ),
                dense_text_score=0.9,
                sparse_score=0.8,
                metadata_match=1.0,
                channel_sources=["dense", "sparse"],
            )
        ],
        channel_orders={"dense": ["offer-source-1"]},
        expected_spu_ids=["gold-spu-1"],
        expected_sku_ids=["gold-sku-1"],
        expected_top_sku_ids=["gold-sku-1"],
        meta=EvalSampleMeta(
            dataset_version="1.0.0",
            split="holdout",
            category_id="headphone",
            subject_ids=["gold-spu-1"],
            source_refs=["source-1"],
            label_source="adjudicated",
        ),
    )

    with pytest.raises(ValueError, match="策略样本候选缺少 Gold 映射"):
        evaluate_retrieval_strategies([sample])
