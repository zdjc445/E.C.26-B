"""确定性领域组件的本地延迟基线。

默认基准只运行生产 Retrieval 策略和仓库内 seed 夹具，不调用模型或外部服务，也不参与
商品质量发布门禁。显式指定 formal 数据源和 p95 阈值后，才执行独立的延迟门禁。
"""

from __future__ import annotations

import math
import platform
import sys
import time
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from shijiajing_agent.eval_engineering import (
    RetrievalStrategySample,
    rank_retrieval_strategy,
)

BenchmarkStrategy = Literal["weighted", "rrf", "weighted_rerank"]
BenchmarkSource = Literal["seed_offline", "formal"]


class BenchmarkResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy: BenchmarkStrategy
    sample_dataset_count: int = Field(ge=1)
    iteration_count: int = Field(ge=1)
    duration_ms_p50: float = Field(ge=0)
    duration_ms_p95: float = Field(ge=0)
    duration_ms_p99: float = Field(ge=0)
    duration_ms_min: float = Field(ge=0)
    duration_ms_max: float = Field(ge=0)


class BenchmarkReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    generated_at: str = Field(min_length=1)
    source: BenchmarkSource = "seed_offline"
    warmup_count: int = Field(ge=0)
    iteration_count: int = Field(ge=1)
    results: list[BenchmarkResult] = Field(min_length=1)
    python_version: str = Field(min_length=1)
    platform: str = Field(min_length=1)
    gate_strategy: BenchmarkStrategy | None = None
    gate_max_p95_ms: float | None = Field(default=None, gt=0)
    gate_passed: bool | None = None
    gate_failures: list[str] = Field(default_factory=list[str])


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, math.ceil(fraction * len(ordered)) - 1)
    return ordered[index]


def _measure(
    samples: list[RetrievalStrategySample],
    strategy: BenchmarkStrategy,
    *,
    warmup_count: int,
    iteration_count: int,
) -> BenchmarkResult:
    for _ in range(warmup_count):
        for sample in samples:
            rank_retrieval_strategy(sample, strategy, rrf_k=60, limit=20)

    durations: list[float] = []
    for _ in range(iteration_count):
        started = time.perf_counter_ns()
        for sample in samples:
            rank_retrieval_strategy(sample, strategy, rrf_k=60, limit=20)
        durations.append((time.perf_counter_ns() - started) / 1_000_000)

    return BenchmarkResult(
        strategy=strategy,
        sample_dataset_count=len(samples),
        iteration_count=iteration_count,
        duration_ms_p50=round(_percentile(durations, 0.50), 6),
        duration_ms_p95=round(_percentile(durations, 0.95), 6),
        duration_ms_p99=round(_percentile(durations, 0.99), 6),
        duration_ms_min=round(min(durations), 6),
        duration_ms_max=round(max(durations), 6),
    )


def run_retrieval_benchmark(
    samples: list[RetrievalStrategySample],
    *,
    warmup_count: int = 5,
    iteration_count: int = 30,
    source: BenchmarkSource = "seed_offline",
) -> BenchmarkReport:
    """运行三种生产策略的本地延迟基线。"""
    if not samples:
        raise ValueError("retrieval strategy benchmark 至少需要一条样本")
    if warmup_count < 0:
        raise ValueError("warmup_count 不能小于 0")
    if iteration_count < 1:
        raise ValueError("iteration_count 必须大于 0")
    strategies: tuple[BenchmarkStrategy, ...] = ("weighted", "rrf", "weighted_rerank")
    return BenchmarkReport(
        generated_at=datetime.now(UTC).isoformat(timespec="seconds"),
        source=source,
        warmup_count=warmup_count,
        iteration_count=iteration_count,
        results=[
            _measure(
                samples,
                strategy,
                warmup_count=warmup_count,
                iteration_count=iteration_count,
            )
            for strategy in strategies
        ],
        python_version=sys.version.split()[0],
        platform=platform.platform(),
    )


def apply_latency_gate(
    report: BenchmarkReport,
    *,
    strategy: BenchmarkStrategy,
    max_p95_ms: float,
) -> BenchmarkReport:
    """对显式 formal benchmark 应用 p95 门禁；seed/offline 不得进入该路径。"""
    if report.source != "formal":
        raise ValueError("性能门禁只允许 source=formal，seed/offline 基线不得作为发布门禁")
    if not math.isfinite(max_p95_ms) or max_p95_ms <= 0:
        raise ValueError("max_p95_ms 必须是有限正数")
    result = next((item for item in report.results if item.strategy == strategy), None)
    if result is None:
        raise ValueError(f"benchmark 缺少门禁策略结果: {strategy}")
    failures: list[str] = []
    if result.duration_ms_p95 > max_p95_ms:
        failures.append(
            f"{strategy}.p95={result.duration_ms_p95:g}ms > max_p95_ms={max_p95_ms:g}ms"
        )
    return report.model_copy(
        update={
            "gate_strategy": strategy,
            "gate_max_p95_ms": max_p95_ms,
            "gate_passed": not failures,
            "gate_failures": failures,
        }
    )


def benchmark_report_to_markdown(report: BenchmarkReport) -> str:
    lines = [
        "# Retrieval 本地延迟基线",
        "",
        f"- 生成时间：{report.generated_at}",
        f"- 数据来源：{report.source}",
        f"- warmup：{report.warmup_count}",
        f"- iterations：{report.iteration_count}",
        f"- Python：{report.python_version}",
        f"- 平台：{report.platform}",
        "",
        "| strategy | dataset rows | iterations | p50 ms | p95 ms | p99 ms | min ms | max ms |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for result in report.results:
        lines.append(
            f"| {result.strategy} | {result.sample_dataset_count} | {result.iteration_count} | "
            f"{result.duration_ms_p50:.6f} | {result.duration_ms_p95:.6f} | "
            f"{result.duration_ms_p99:.6f} | {result.duration_ms_min:.6f} | "
            f"{result.duration_ms_max:.6f} |"
        )
    if report.gate_passed is None:
        gate_line = "性能门禁：未启用"
    elif (
        report.gate_passed
        and report.gate_strategy is not None
        and report.gate_max_p95_ms is not None
    ):
        gate_line = f"性能门禁：✅ {report.gate_strategy} p95 <= {report.gate_max_p95_ms:g} ms"
    elif report.gate_passed:
        gate_line = "性能门禁：✅"
    else:
        gate_line = "性能门禁：❌ " + "；".join(report.gate_failures)
    lines.extend(
        [
            "",
            gate_line,
            (
                "本报告只记录当前机器上的 seed/offline 领域组件基线，不是正式线上数据性能门禁。"
                if report.source == "seed_offline"
                else "本报告标记为 formal；只有显式性能门禁通过时才可作为延迟验收证据。"
            ),
        ]
    )
    return "\n".join(lines) + "\n"
