"""离线评测 CLI（方案 §22）。

用法：``shijiajing-eval [--datasets-dir DIR] [--report-dir DIR] [--live] [--frozen]``

- 默认 offline：只读数据集内 ``recorded`` 冻结输出，下游领域逻辑全部真实运行。
- ``--live``：需要完整外部配置（模型、检索、checkpoint），通过 facade 与检索
  适配器实时产出并回填 recorded；可用 ``--freeze-dir`` 把 live 输出冻结为数据集。
- ``--frozen``：门禁通过后把本次报告写入 ``reports/frozen_eval_report.md``。

退出码：0 = 门禁通过；1 = 阻断指标未达标；2 = 配置/数据集错误。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from shijiajing_agent.config import load_settings
from shijiajing_agent.contracts import AgentRequest, AgentStatus, RetrievalQuery
from shijiajing_agent.deps import make_deps
from shijiajing_agent.domain.filters import offer_matches_hard_filters
from shijiajing_agent.domain.taxonomy import load_taxonomy
from shijiajing_agent.evals import (
    DATASET_FILES,
    EvalReport,
    RetrievalRecorded,
    RetrievalSample,
    WorkflowRecorded,
    WorkflowSample,
    compute_report,
    default_datasets_dir,
    gate_check,
    load_all_datasets,
    report_to_json,
    report_to_markdown,
)
from shijiajing_agent.facade import AgentFacade

_EXIT_PASS = 0
_EXIT_GATE_FAIL = 1
_EXIT_CONFIG_ERROR = 2


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="识价镜 Agent 离线评测（§22）")
    parser.add_argument("--datasets-dir", type=Path, default=default_datasets_dir())
    parser.add_argument("--report-dir", type=Path, default=Path("reports"))
    parser.add_argument(
        "--live",
        action="store_true",
        help="通过真实适配器实时评测（需要 SHIJIAJING_* 外部配置）",
    )
    parser.add_argument(
        "--freeze-dir",
        type=Path,
        default=None,
        help="与 --live 搭配：把实时输出冻结为数据集副本",
    )
    parser.add_argument(
        "--frozen",
        action="store_true",
        help="门禁通过后写入 reports/frozen_eval_report.md（冻结报告）",
    )
    parser.add_argument(
        "--no-gate",
        action="store_true",
        help="不按 §22.3 门禁判定退出码（仅生成报告）",
    )
    return parser.parse_args(argv)


# ---------------------------------------------------------------------------
# live 评测：把真实输出回填为 recorded
# ---------------------------------------------------------------------------


async def _live_retrieval(sample: RetrievalSample, deps: Any) -> RetrievalRecorded:
    query = RetrievalQuery.model_validate(sample.query)
    result = await deps.retrieval.search(query, top_k=50, union_limit=100)
    top_sku: list[str] = []
    sku_ids: list[str] = []
    spu_ids: list[str] = []
    for c in result.candidates[:50]:
        sku = c.offer.sku_key or c.offer.offer_id
        if sku and sku not in top_sku:
            top_sku.append(sku)
        spu = c.offer.same_item_key or c.offer.offer_id
        if spu and spu not in spu_ids:
            spu_ids.append(spu)
    for c in result.candidates:
        sku = c.offer.sku_key or c.offer.offer_id
        if sku and sku not in sku_ids:
            sku_ids.append(sku)
    hard_ok = all(
        offer_matches_hard_filters(c.offer, query.hard_filters) for c in result.candidates[:50]
    )
    return RetrievalRecorded(
        top_sku_ids=top_sku,
        sku_ids=sku_ids,
        spu_ids=spu_ids,
        hard_filter_satisfied=hard_ok,
        fallback_used=result.fallback_used or None,
    )


async def _live_workflow(sample: WorkflowSample, facade: AgentFacade) -> WorkflowRecorded:
    latencies: list[float] = []
    last: Any = None
    for i, raw in enumerate(sample.turns):
        request = AgentRequest.model_validate(raw)
        if not request.request_id:
            request = request.model_copy(update={"request_id": f"eval-{sample.id}-t{i}"})
        started = time.perf_counter()
        last = await facade.run(request)
        latencies.append((time.perf_counter() - started) * 1000.0)
    assert last is not None
    status = last.status.value
    groups = [g.group.group_id for g in last.groups]
    has_correction = any(t.get("correction") for t in sample.turns)
    return WorkflowRecorded(
        status=status,
        clarification=last.status == AgentStatus.CLARIFICATION,
        group_ids=groups,
        correction_success=last.status != AgentStatus.FAILED if has_correction else None,
        # VLM 调用次数与降级标记需要模型/检索插桩透出，见 docs/evaluation.md
        vlm_called_after_correction=None,
        fallback_used=None,
        model_calls_per_turn=None,
        state_exact=set(groups) == set(sample.expected_group_ids),
        latency_ms=latencies,
    )


async def _run_live(datasets: dict[str, list[Any]], settings: Any) -> dict[str, list[Any]]:
    """通过真实适配器运行 workflow 与 retrieval 数据集，回填 recorded。"""
    deps = make_deps(settings)
    facade = AgentFacade(deps)
    for sample in datasets.get("workflow") or []:
        sample.recorded = await _live_workflow(sample, facade)
    for sample in datasets.get("retrieval") or []:
        sample.recorded = await _live_retrieval(sample, deps)
    return datasets


def _freeze_datasets(datasets: dict[str, list[Any]], out_dir: Path) -> None:
    """把（live 回填后的）数据集写出为 jsonl 副本，供后续离线复现。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    for kind, (filename, _) in DATASET_FILES.items():
        rows = datasets.get(kind) or []
        with (out_dir / filename).open("w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(row.model_dump_json(exclude_none=True) + "\n")
    (out_dir / "README.md").write_text(
        "本目录由 `shijiajing-eval --live --freeze-dir` 生成：\n"
        "- recorded 字段为真实适配器在评测时刻的输出（冻结快照）。\n"
        "- 商品数据来源以生成环境为准，不得与真实平台数据混淆。\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    # Windows 控制台默认 GBK，无法输出 ✅/中文；统一按 UTF-8 打印
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")
    args = _parse_args(argv)
    datasets_dir: Path = args.datasets_dir
    report_dir: Path = args.report_dir

    if not datasets_dir.exists():
        print(f"数据集目录不存在：{datasets_dir}", file=sys.stderr)
        return _EXIT_CONFIG_ERROR

    datasets = load_all_datasets(datasets_dir)
    total = sum(len(rows) for rows in datasets.values())
    if total == 0:
        print(f"数据集目录为空：{datasets_dir}", file=sys.stderr)
        return _EXIT_CONFIG_ERROR

    settings = load_settings()
    source = "live" if args.live else "offline"
    if args.live:
        try:
            datasets = asyncio.run(_run_live(datasets, settings))
        except ValueError as exc:
            print(f"live 评测配置错误：{exc}", file=sys.stderr)
            return _EXIT_CONFIG_ERROR
        if args.freeze_dir is not None:
            _freeze_datasets(datasets, args.freeze_dir)

    report: EvalReport = compute_report(
        datasets,
        load_taxonomy(settings.taxonomy_path_resolved),
        source=source,
        generated_at=datetime.now(UTC).isoformat(timespec="seconds"),
        datasets_dir=datasets_dir,
    )

    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "eval_report.json").write_text(
        json.dumps(report_to_json(report), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (report_dir / "eval_report.md").write_text(report_to_markdown(report), encoding="utf-8")
    print(f"评测报告：{report_dir / 'eval_report.md'}（数据来源：{source}）")

    if report.gate:
        print("✅ 阻断指标全部达标")
    else:
        print("❌ 存在阻断指标未达标")
        for m in report.blocking_failures:
            threshold = m.threshold
            if threshold is None or m.value is None:  # 属性保证，窄化防御
                continue
            print(f"  - {m.name}: {m.value:g}（要求 {threshold.op} {threshold.value:g}）")
        for m in report.blocking_pending:
            print(f"  - {m.name}: 未测量（需 live 数据）")

    if args.frozen and report.gate:
        frozen = report_dir / "frozen_eval_report.md"
        frozen.write_text(report_to_markdown(report), encoding="utf-8")
        print(f"冻结报告已写入：{frozen}")

    if args.no_gate:
        return _EXIT_PASS
    return _EXIT_PASS if gate_check(report) else _EXIT_GATE_FAIL


if __name__ == "__main__":
    sys.exit(main())
