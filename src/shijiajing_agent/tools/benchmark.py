"""运行确定性 Retrieval 本地延迟基线。"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, cast

from shijiajing_agent.benchmark import (
    BenchmarkReport,
    apply_latency_gate,
    benchmark_report_to_markdown,
    run_retrieval_benchmark,
)
from shijiajing_agent.eval_data import OfferGoldLabel, load_jsonl_rows, load_manifest
from shijiajing_agent.eval_engineering import RetrievalStrategySample
from shijiajing_agent.eval_freeze import validate_frozen_dataset_metadata
from shijiajing_agent.evals import default_datasets_dir, load_all_datasets
from shijiajing_agent.tools.cli_support import configure_utf8_output

_REPORT_FILENAMES = ("benchmark_report.json", "benchmark_report.md")


def _invalidate_report_artifacts(report_dir: Path) -> None:
    for filename in _REPORT_FILENAMES:
        (report_dir / filename).unlink(missing_ok=True)


def _commit_report_artifacts(report_dir: Path, report: BenchmarkReport) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    staging_dir = Path(tempfile.mkdtemp(prefix=".benchmark-report.", dir=report_dir))
    try:
        (staging_dir / "benchmark_report.json").write_text(
            json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (staging_dir / "benchmark_report.md").write_text(
            benchmark_report_to_markdown(report), encoding="utf-8"
        )
        for filename in _REPORT_FILENAMES:
            (staging_dir / filename).replace(report_dir / filename)
    finally:
        if staging_dir.exists():
            shutil.rmtree(staging_dir)


def _require_formal_benchmark_dataset(datasets_dir: Path) -> None:
    """拒绝把 seed 或未校验目录标记为 formal 性能数据。"""
    manifest = load_manifest(datasets_dir)
    if manifest is None:
        raise ValueError("source=formal 要求 datasets-dir 包含 manifest.json")
    if (
        manifest.trust_level != "frozen"
        or manifest.label_method != "adjudicated"
        or not manifest.gate_eligible
    ):
        raise ValueError(
            "source=formal 要求 manifest 为 trust_level=frozen、"
            "label_method=adjudicated、gate_eligible=true"
        )
    strategy_filename = "retrieval_strategy_dataset.jsonl"
    if strategy_filename not in manifest.files or not (datasets_dir / strategy_filename).is_file():
        raise ValueError(f"formal 数据集缺少 {strategy_filename} 或未纳入 manifest.files")
    errors = validate_frozen_dataset_metadata(datasets_dir, manifest)
    if errors:
        raise ValueError("formal 数据集冻结校验失败：" + "；".join(errors[:5]))
    labels_path = datasets_dir / "offer_labels.jsonl"
    if labels_path.is_file():
        labels = load_jsonl_rows(labels_path, OfferGoldLabel)
        if any(label.label_source != "adjudicated" for label in labels):
            raise ValueError("formal 数据集的 offer_labels 必须全部为 adjudicated")
    datasets = load_all_datasets(datasets_dir)
    strategy_rows = cast(list[RetrievalStrategySample], datasets.get("retrieval_strategy", []))
    if not strategy_rows:
        raise ValueError("formal 数据集的 retrieval_strategy_dataset.jsonl 不能为空")
    for row in strategy_rows:
        meta = getattr(row, "meta", None)
        if meta is None or meta.label_source != "adjudicated":
            row_id = row.model_dump(mode="json").get("id", "<unknown>")
            raise ValueError(
                f"formal retrieval_strategy {row_id} 的 meta.label_source 必须为 adjudicated"
            )
        candidate_ids = {candidate.offer.offer_id for candidate in row.candidates}
        if (
            set(row.gold_spu_by_offer_id) != candidate_ids
            or set(row.gold_sku_by_offer_id) != candidate_ids
        ):
            raise ValueError(
                f"formal retrieval_strategy {row.id} 必须为每个候选提供完整 Gold SPU/SKU 映射"
            )


def _args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="shijiajing-benchmark")
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=Path("reports"),
        help="报告输出目录",
    )
    parser.add_argument("--warmup", type=int, default=5, help="预热迭代次数")
    parser.add_argument("--iterations", type=int, default=30, help="正式迭代次数")
    parser.add_argument(
        "--datasets-dir",
        type=Path,
        default=None,
        help="包含 retrieval_strategy_dataset.jsonl 的数据集目录；formal 必须显式提供",
    )
    parser.add_argument(
        "--source",
        choices=("seed_offline", "formal"),
        default="seed_offline",
        help="数据来源；默认 seed_offline 不参与性能门禁",
    )
    parser.add_argument(
        "--gate-strategy",
        choices=("weighted", "rrf", "weighted_rerank"),
        default="weighted",
        help="formal 性能门禁检查的策略",
    )
    parser.add_argument(
        "--max-p95-ms",
        type=float,
        default=None,
        help="formal 性能门禁的最大 p95 毫秒数；seed_offline 禁止提供",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    configure_utf8_output()
    args = _args(argv)
    try:
        _invalidate_report_artifacts(args.report_dir)
        max_p95_ms: float | None = None
        if args.source == "formal":
            if args.datasets_dir is None:
                raise ValueError("source=formal 必须显式指定 --datasets-dir")
            if args.max_p95_ms is None:
                raise ValueError("source=formal 必须显式指定 --max-p95-ms")
            max_p95_ms = cast(float, args.max_p95_ms)
        elif args.max_p95_ms is not None:
            raise ValueError("seed_offline 禁止使用 --max-p95-ms；请显式指定 source=formal")

        datasets_dir = args.datasets_dir or default_datasets_dir()
        if args.source == "formal":
            _require_formal_benchmark_dataset(datasets_dir)
        datasets: dict[str, list[Any]] = load_all_datasets(datasets_dir)
        samples = cast(list[RetrievalStrategySample], datasets.get("retrieval_strategy", []))
        report = run_retrieval_benchmark(
            samples,
            warmup_count=args.warmup,
            iteration_count=args.iterations,
            source=args.source,
        )
        if args.source == "formal":
            if max_p95_ms is None:
                raise ValueError("source=formal 必须显式指定 --max-p95-ms")
            report = apply_latency_gate(
                report,
                strategy=args.gate_strategy,
                max_p95_ms=max_p95_ms,
            )
        _commit_report_artifacts(args.report_dir, report)
        if report.gate_passed is False:
            print("性能门禁失败：" + "；".join(report.gate_failures), file=sys.stderr)
            return 1
        print(f"基线报告：{args.report_dir / 'benchmark_report.md'}")
        return 0
    except (OSError, ValueError) as exc:
        print(f"benchmark 配置或执行失败：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
