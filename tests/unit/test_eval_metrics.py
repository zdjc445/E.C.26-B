"""评测指标单元测试（§22）：纯函数与离线评测器行为。

重点验证：
- 各指标函数（_prf/_recall_at/_mrr/_ndcg/_ece）的边界行为；
- 数据集严格加载（extra="forbid"）与摘要稳定性；
- 离线评测器对种子数据集产出达标报告（阻断指标全部通过）。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from shijiajing_agent.evals import (
    RecognitionSample,
    SameItemSample,
    _ece,
    _mrr,
    _ndcg,
    _prf,
    _recall_at,
    compute_report,
    dataset_digest,
    default_datasets_dir,
    evaluate_same_item,
    gate_check,
    load_all_datasets,
    load_dataset,
)


def test_prf_basic() -> None:
    assert _prf(9, 1, 1) == pytest.approx((0.9, 0.9, 0.9))
    assert _prf(0, 0, 0) == (0.0, 0.0, 0.0)
    assert _prf(2, 0, 0) == (1.0, 1.0, 1.0)


def test_recall_at() -> None:
    ranked = ["a", "b", "c", "d"]
    assert _recall_at(ranked, ["a"], 3) == 1.0
    assert _recall_at(ranked, ["a", "d"], 2) == 0.5
    assert _recall_at(ranked, ["z"], 4) == 0.0
    # 空期望视为不需要召回（避免 0/0）
    assert _recall_at(ranked, [], 4) == 1.0
    # k=0 边界
    assert _recall_at(ranked, ["a"], 0) == 0.0


def test_mrr() -> None:
    assert _mrr(["a", "b"], ["a"]) == 1.0
    assert _mrr(["x", "a", "b"], ["a"]) == 0.5
    assert _mrr(["x"], ["a"]) == 0.0
    assert _mrr([], ["a"]) == 0.0


def test_ndcg() -> None:
    # 完全命中且顺序与偏好一致 → 1.0
    assert _ndcg(["a", "b", "c"], ["a", "b", "c"], 3) == pytest.approx(1.0)
    # 逆序 → 低于 1
    assert _ndcg(["c", "b", "a"], ["a", "b", "c"], 3) < 1.0
    # 无命中 → 0
    assert _ndcg(["x", "y"], ["a", "b"], 2) == 0.0
    # k=0 边界
    assert _ndcg(["a"], ["a"], 0) == 0.0


def test_ece_perfect_and_worst() -> None:
    # 每箱内 精度 == 平均置信度（0.5 箱中 2 对 1 对错）→ ECE = 0
    assert _ece([0.5, 0.5, 0.5, 0.5], [True, False, True, False]) == pytest.approx(0.0)
    # 全部 1.0 但全错 → ECE = 1（完全失准）
    assert _ece([1.0, 1.0], [False, False]) == pytest.approx(1.0)
    # 单调正确的高置信样本：低箱的 1.0 精度相对平均置信度有偏差（有意义的 ECE）
    assert 0.0 < _ece([0.9, 0.8, 0.7, 0.6], [True, True, True, True]) < 1.0
    # 空输入
    assert _ece([], []) == 0.0


def test_dataset_digest_stable(tmp_path: Path) -> None:
    path = tmp_path / "samples.jsonl"
    path.write_text('{"id": "a"}\n{"id": "b"}\n', encoding="utf-8")
    assert dataset_digest(path) == dataset_digest(path)
    # 内容变化后摘要必须变化
    digest_before = dataset_digest(path)
    path.write_text('{"id": "a"}\n{"id": "c"}\n', encoding="utf-8")
    assert dataset_digest(path) != digest_before


def test_load_dataset_forbids_extra_fields(tmp_path: Path) -> None:
    path = tmp_path / "recognition.jsonl"
    path.write_text(
        '{"id": "r-1", "image": "img://1", "text": "t",'
        ' "expected": {"category_id": "headphone"}, "recorded": null,'
        ' "unknown_extra": 1}\n',
        encoding="utf-8",
    )
    with pytest.raises(ValidationError):
        load_dataset(path, RecognitionSample)


def test_load_all_datasets_seed_dir() -> None:
    """种子数据集可完整加载，且每类都有 recorded 行。"""
    from shijiajing_agent.evals import default_datasets_dir

    datasets = load_all_datasets(default_datasets_dir())
    assert set(datasets) == {
        "recognition",
        "intent",
        "retrieval",
        "same_item",
        "ranking",
        "end_to_end",
        "memory",
        "multi_agent",
        "interrupt",
        "cache",
        "retrieval_strategy",
    }
    for rows in datasets.values():
        assert rows, "每个数据集至少一行"
    # recorded 型数据集（除按构造评测的 same_item_pairs/ranking）都应含 recorded 行
    for kind in ("recognition", "intent", "retrieval", "end_to_end"):
        rows = datasets[kind]
        assert any(getattr(r, "recorded", None) is not None for r in rows), kind


def test_evaluate_same_item_seed_pairs(taxonomy) -> None:
    """种子同款对：领域判定与期望全部一致 → 阻断指标达标。"""
    from shijiajing_agent.evals import default_datasets_dir

    pairs_path = default_datasets_dir() / "same_item_pairs.jsonl"
    samples = load_dataset(pairs_path, SameItemSample)
    metrics = evaluate_same_item(samples, taxonomy, source="offline")
    by_name = {m.name: m for m in metrics}
    assert by_name["same_item_pairwise_precision"].value == pytest.approx(1.0)
    assert by_name["false_comparison_rate"].value == pytest.approx(0.0)
    assert by_name["same_item_pairwise_precision"].passed is True
    assert by_name["false_comparison_rate"].passed is True


def test_gate_check_seed_report(taxonomy) -> None:
    """完整离线评测：阻断指标全部达标，报告 gate=True。"""
    from shijiajing_agent.evals import default_datasets_dir

    datasets = load_all_datasets(default_datasets_dir())
    report = compute_report(
        datasets,
        taxonomy,
        source="offline",
        generated_at="2026-08-13T00:00:00+00:00",
        datasets_dir=default_datasets_dir(),
    )
    assert report.gate is True
    assert gate_check(report) is True
    assert report.blocking_failures == []
    assert report.blocking_pending == []
    # 非阻断指标的未测量状态如实呈现（pending > 0），不得掩盖
    all_blocking = [m for m in report.metrics if m.threshold is not None and m.threshold.blocking]
    assert len(all_blocking) == 4
    for m in all_blocking:
        assert m.passed is True


def test_release_gate_eligibility_requires_manifest_gate_flag(taxonomy) -> None:
    datasets = load_all_datasets(default_datasets_dir())
    report = compute_report(
        datasets,
        taxonomy,
        source="offline",
        generated_at="2026-08-13T00:00:00+00:00",
        datasets_dir=default_datasets_dir(),
        trust_level="frozen",
        label_method="adjudicated",
        gate_eligible=False,
    )

    assert report.release_gate_eligible is False
    assert report.release_gate_passed is False


def test_release_gate_never_passes_with_pending_blocking_metric(taxonomy) -> None:
    datasets = load_all_datasets(default_datasets_dir())
    datasets["retrieval"] = [
        sample.model_copy(update={"recorded": None}) for sample in datasets["retrieval"]
    ]
    report = compute_report(
        datasets,
        taxonomy,
        source="offline",
        generated_at="2026-08-13T00:00:00+00:00",
        datasets_dir=default_datasets_dir(),
        trust_level="frozen",
        label_method="adjudicated",
        gate_eligible=True,
    )

    assert report.metric_gate_passed is True
    assert report.blocking_pending
    assert report.release_gate_passed is False
