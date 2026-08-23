"""本地 Retrieval 延迟基线测试。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from shijiajing_agent.benchmark import (
    apply_latency_gate,
    benchmark_report_to_markdown,
    run_retrieval_benchmark,
)
from shijiajing_agent.eval_data import DatasetManifest, EvalSampleMeta, compute_files_sha256
from shijiajing_agent.eval_engineering import RetrievalStrategySample
from shijiajing_agent.evals import default_datasets_dir, load_all_datasets
from shijiajing_agent.tools import cli_support
from shijiajing_agent.tools.benchmark import main


def _samples() -> list[RetrievalStrategySample]:
    datasets = load_all_datasets(default_datasets_dir())
    return [RetrievalStrategySample.model_validate(row) for row in datasets["retrieval_strategy"]]


def test_retrieval_benchmark_reports_three_strategies() -> None:
    report = run_retrieval_benchmark(_samples(), warmup_count=1, iteration_count=3)

    assert [result.strategy for result in report.results] == [
        "weighted",
        "rrf",
        "weighted_rerank",
    ]
    for result in report.results:
        assert result.sample_dataset_count == 2
        assert result.iteration_count == 3
        assert result.duration_ms_min <= result.duration_ms_p50
        assert result.duration_ms_p50 <= result.duration_ms_p95
        assert result.duration_ms_p95 <= result.duration_ms_p99
        assert result.duration_ms_p99 <= result.duration_ms_max
    assert "seed/offline" in benchmark_report_to_markdown(report)


def test_benchmark_cli_writes_machine_readable_report(tmp_path: Path) -> None:
    assert main(["--report-dir", str(tmp_path), "--warmup", "0", "--iterations", "2"]) == 0

    report = json.loads((tmp_path / "benchmark_report.json").read_text(encoding="utf-8"))
    assert report["source"] == "seed_offline"
    assert report["iteration_count"] == 2
    assert (tmp_path / "benchmark_report.md").exists()


def test_benchmark_cli_reconfigures_output_streams(monkeypatch, tmp_path: Path) -> None:
    class Stream:
        def __init__(self) -> None:
            self.calls: list[dict[str, str]] = []
            self.output = ""

        def reconfigure(self, **kwargs: str) -> None:
            self.calls.append(kwargs)

        def write(self, value: str) -> int:
            self.output += value
            return len(value)

        def flush(self) -> None:
            return None

    stdout = Stream()
    stderr = Stream()
    monkeypatch.setattr(cli_support.sys, "stdout", stdout)
    monkeypatch.setattr(cli_support.sys, "stderr", stderr)

    assert main(["--report-dir", str(tmp_path)]) == 0

    assert stdout.calls == [{"encoding": "utf-8", "errors": "replace"}]
    assert stderr.calls == [{"encoding": "utf-8", "errors": "replace"}]


def test_benchmark_cli_removes_stale_report_on_configuration_failure(tmp_path: Path) -> None:
    (tmp_path / "benchmark_report.json").write_text("stale", encoding="utf-8")
    (tmp_path / "benchmark_report.md").write_text("stale", encoding="utf-8")

    assert main(["--source", "formal", "--report-dir", str(tmp_path)]) == 2
    assert not (tmp_path / "benchmark_report.json").exists()
    assert not (tmp_path / "benchmark_report.md").exists()


def test_latency_gate_is_explicit_and_reports_pass_or_failure() -> None:
    report = run_retrieval_benchmark(_samples(), warmup_count=0, iteration_count=2, source="formal")
    weighted = next(result for result in report.results if result.strategy == "weighted")

    passed = apply_latency_gate(
        report,
        strategy="weighted",
        max_p95_ms=weighted.duration_ms_p95 + 1.0,
    )
    assert passed.gate_passed is True
    assert passed.gate_failures == []
    assert "性能门禁：✅" in benchmark_report_to_markdown(passed)

    failed = apply_latency_gate(
        report,
        strategy="weighted",
        max_p95_ms=max(weighted.duration_ms_p95 / 2, 0.000001),
    )
    assert failed.gate_passed is False
    assert failed.gate_failures
    assert "性能门禁：❌" in benchmark_report_to_markdown(failed)


def test_latency_gate_rejects_seed_source() -> None:
    report = run_retrieval_benchmark(_samples(), warmup_count=0, iteration_count=1)
    with pytest.raises(ValueError, match="source=formal"):
        apply_latency_gate(report, strategy="weighted", max_p95_ms=100.0)


def test_benchmark_cli_rejects_implicit_formal_gate(tmp_path: Path) -> None:
    assert main(["--source", "formal", "--max-p95-ms", "100"]) == 2
    assert main(["--max-p95-ms", "100", "--report-dir", str(tmp_path)]) == 2
    assert (
        main(
            [
                "--source",
                "formal",
                "--datasets-dir",
                str(default_datasets_dir()),
                "--max-p95-ms",
                "100",
                "--report-dir",
                str(tmp_path),
            ]
        )
        == 2
    )


def test_benchmark_cli_runs_formal_gate_with_frozen_strategy_fixture(tmp_path: Path) -> None:
    datasets_dir = tmp_path / "frozen"
    datasets_dir.mkdir()
    strategy_rows = []
    for line in (
        (default_datasets_dir() / "retrieval_strategy_dataset.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ):
        row = json.loads(line)
        row["meta"] = EvalSampleMeta(
            dataset_version="1.0.0",
            split="holdout",
            category_id="headphone",
            subject_ids=["spu:formal-fixture"],
            source_refs=["source:formal-fixture"],
            label_source="adjudicated",
        ).model_dump(mode="json")
        row["gold_spu_by_offer_id"] = {
            candidate["offer"]["offer_id"]: candidate["offer"]["same_item_key"]
            for candidate in row["candidates"]
        }
        row["gold_sku_by_offer_id"] = {
            candidate["offer"]["offer_id"]: candidate["offer"]["sku_key"]
            for candidate in row["candidates"]
        }
        strategy_rows.append(row)
    (datasets_dir / "retrieval_strategy_dataset.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in strategy_rows) + "\n",
        encoding="utf-8",
    )
    (datasets_dir / "adjudication_record.json").write_text(
        json.dumps(
            {
                "record_id": "adj-formal-fixture",
                "dataset_id": "formal-fixture",
                "dataset_version": "1.0.0",
                "decision": "approved",
                "review_scope": "all_rows",
                "adjudicator_ids": ["reviewer-a", "reviewer-b"],
                "reviewed_at": "2026-08-22T00:00:00+00:00",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    manifest = DatasetManifest(
        dataset_id="formal-fixture",
        dataset_schema_version="1.0",
        dataset_version="1.0.0",
        taxonomy_version="taxonomy-fixture",
        trust_level="frozen",
        label_method="adjudicated",
        gate_eligible=True,
        created_at="2026-08-22T00:00:00+00:00",
        as_of="2026-08-22T00:00:00+00:00",
        categories={"headphone": 2},
        counts_by_file={"retrieval_strategy_dataset.jsonl": len(strategy_rows)},
        counts_by_split={"holdout": len(strategy_rows)},
        counts_by_platform={},
        offer_count=0,
        spu_count=0,
        asset_count=0,
        files=compute_files_sha256(datasets_dir),
    )
    (datasets_dir / "manifest.json").write_text(
        manifest.model_dump_json(indent=2), encoding="utf-8"
    )

    report_dir = tmp_path / "report"
    assert (
        main(
            [
                "--source",
                "formal",
                "--datasets-dir",
                str(datasets_dir),
                "--max-p95-ms",
                "1000",
                "--warmup",
                "0",
                "--iterations",
                "2",
                "--report-dir",
                str(report_dir),
            ]
        )
        == 0
    )
    report = json.loads((report_dir / "benchmark_report.json").read_text(encoding="utf-8"))
    assert report["source"] == "formal"
    assert report["gate_passed"] is True
