"""评测 CLI（方案 §22 + Phase 1 §10–§11）。

用法：``shijiajing-eval [--datasets-dir DIR] [--report-dir DIR] [--live]
  [--assets-dir DIR] [--output-datasets-dir DIR] [--frozen] [--no-gate]``

- 默认 offline：只读数据集内 ``recorded`` 冻结输出，下游领域逻辑全部真实运行。
- ``--live``：需要完整外部配置（模型、检索、checkpoint），通过 facade 与检索
  适配器实时产出并回填 recorded；可用 ``--output-datasets-dir`` 把 live 输出冻结为
  数据集副本（``--freeze-dir`` 为兼容别名，已标记 deprecated）。
- ``--frozen``：仅当 manifest 为 frozen、``label_method=adjudicated`` 且
  ``gate_eligible=true`` 时，
  门禁通过后写入 ``reports/frozen_eval_report.md``；provisional 数据返回配置错误 2。
- provisional 数据默认退出码为 1（不可作为发布门禁）；``--no-gate`` 只用于临时观察。

退出码：0 = 门禁通过（frozen）/ --no-gate 成功生成报告；1 = 阻断指标未达标或
provisional 默认；2 = 配置/数据集错误。
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from shijiajing_agent.asyncio_compat import run as run_async
from shijiajing_agent.config import Settings, load_settings
from shijiajing_agent.deps import make_deps
from shijiajing_agent.domain.taxonomy import load_taxonomy
from shijiajing_agent.engineering_eval import (
    engineering_report_to_markdown,
    evaluate_engineering_datasets,
)
from shijiajing_agent.eval_data import (
    GATE_ELIGIBLE_FALSE,
    LABEL_METHOD_ADJUDICATED,
    LABEL_METHOD_AGENT,
    TRUST_LEVEL_FROZEN,
    TRUST_LEVEL_PROVISIONAL,
    load_manifest,
)
from shijiajing_agent.eval_engineering import (
    RetrievalStrategySample,
    evaluate_retrieval_strategies,
    retrieval_strategy_report_to_markdown,
)
from shijiajing_agent.eval_freeze import validate_frozen_dataset_metadata
from shijiajing_agent.evals import (
    DATASET_FILES,
    EvalReport,
    compute_report,
    default_datasets_dir,
    gate_check,
    load_all_datasets,
    report_to_json,
    report_to_markdown,
)
from shijiajing_agent.evals_live import run_live_paths, write_run_manifest
from shijiajing_agent.runtime import open_agent_runtime
from shijiajing_agent.tools.cli_support import configure_utf8_output

_EXIT_PASS = 0
_EXIT_GATE_FAIL = 1
_EXIT_CONFIG_ERROR = 2
_FROZEN_REPORT_FILENAME = "frozen_eval_report.md"
_REPORT_ARTIFACT_FILENAMES = (
    "eval_report.json",
    "eval_report.md",
    "retrieval_strategy_comparison.json",
    "retrieval_strategy_comparison.md",
    "engineering_eval_report.json",
    "engineering_eval_report.md",
)

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _invalidate_frozen_report(report_dir: Path) -> None:
    """使上一次 frozen 结果失效，避免失败运行留下可误用的旧报告。"""
    frozen_report = report_dir / _FROZEN_REPORT_FILENAME
    if not frozen_report.exists():
        return
    if not frozen_report.is_file():
        raise ValueError(f"frozen 报告路径不是文件，无法失效：{frozen_report}")
    try:
        frozen_report.unlink()
    except OSError as exc:
        raise ValueError(f"无法使旧 frozen 报告失效：{frozen_report}: {exc}") from exc


def _invalidate_report_artifacts(report_dir: Path) -> None:
    """清除上一次评测生成的已知报告，避免可选数据缺失时残留旧结果。"""
    if report_dir.exists() and not report_dir.is_dir():
        raise ValueError(f"报告路径不是目录：{report_dir}")
    for filename in _REPORT_ARTIFACT_FILENAMES:
        artifact = report_dir / filename
        if not artifact.exists():
            continue
        if not artifact.is_file():
            raise ValueError(f"评测报告路径不是文件，无法失效：{artifact}")
        try:
            artifact.unlink()
        except OSError as exc:
            raise ValueError(f"无法使旧评测报告失效：{artifact}: {exc}") from exc


def _write_frozen_report(report_dir: Path, report: EvalReport) -> Path:
    """先写同目录临时文件，再原子替换冻结报告。"""
    frozen_report = report_dir / _FROZEN_REPORT_FILENAME
    staging_report: Path | None = None
    try:
        descriptor, staging_name = tempfile.mkstemp(
            prefix=f".{_FROZEN_REPORT_FILENAME}.",
            suffix=".tmp",
            dir=report_dir,
        )
        staging_report = Path(staging_name)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(report_to_markdown(report))
        staging_report.replace(frozen_report)
    except OSError as exc:
        raise ValueError(f"冻结报告写入失败：{frozen_report}: {exc}") from exc
    finally:
        if staging_report is not None:
            try:
                staging_report.unlink(missing_ok=True)
            except OSError:
                pass
    return frozen_report


def _commit_report_artifacts(report_dir: Path, artifacts: dict[str, str]) -> None:
    """先完整写入同目录 staging，再提交本次评测生成的报告文件。"""
    report_dir.mkdir(parents=True, exist_ok=True)
    staging_dir = Path(tempfile.mkdtemp(prefix=".eval-report.", dir=report_dir))
    try:
        for filename, content in artifacts.items():
            relative_path = Path(filename)
            if relative_path.is_absolute() or relative_path.name != filename:
                raise ValueError(f"评测报告文件名必须是单层文件名：{filename}")
            (staging_dir / relative_path).write_text(content, encoding="utf-8")
        for filename in artifacts:
            (staging_dir / filename).replace(report_dir / filename)
    except OSError as exc:
        raise ValueError(f"评测报告 staging 提交失败：{exc}") from exc
    finally:
        if staging_dir.exists():
            shutil.rmtree(staging_dir)


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
        "--assets-dir",
        type=Path,
        default=None,
        help="私有资产目录（recognition live 解析 asset 使用，如 evals/private/.../raw/images）",
    )
    parser.add_argument(
        "--output-datasets-dir",
        type=Path,
        default=None,
        help="与 --live 搭配：把实时输出冻结为数据集副本",
    )
    parser.add_argument(
        "--freeze-dir",
        type=Path,
        default=None,
        help="DEPRECATED: 请改用 --output-datasets-dir（兼容别名）",
    )
    parser.add_argument(
        "--frozen",
        action="store_true",
        help="门禁通过后写入 reports/frozen_eval_report.md（仅 frozen 数据）",
    )
    parser.add_argument(
        "--no-gate",
        action="store_true",
        help="不按门禁判定退出码（仅生成报告；provisional 数据必须配合使用）",
    )
    return parser.parse_args(argv)


# ---------------------------------------------------------------------------
# live 评测：把真实输出回填为 recorded
# ---------------------------------------------------------------------------


async def _run_live(
    datasets: dict[str, list[Any]], settings: Settings, args: argparse.Namespace
) -> tuple[dict[str, list[Any]], list[str]]:
    """通过真实适配器运行六类 live 路径，回填 recorded。

    缺配置时返回 (原数据集, 精确缺失项列表)，指标保持 pending，不写伪 recorded。
    """
    missing = settings.validate(require_real_adapters=True)
    if missing:
        return datasets, [f"SHIJIAJING_{name}" for name in missing]
    deps = make_deps(settings)
    run_id = f"run:{uuid.uuid4().hex[:8]}"
    taxonomy = deps.taxonomy
    async with open_agent_runtime(settings, deps_factory=lambda _settings: deps) as runtime_facade:
        await run_live_paths(
            datasets,
            deps,
            datasets_dir=args.datasets_dir,
            assets_dir=args.assets_dir,
            run_id=run_id,
            runtime_facade=runtime_facade,
        )
    out_dir = args.output_datasets_dir or args.freeze_dir
    if out_dir is not None:

        def finalize(staging_dir: Path) -> None:
            write_run_manifest(
                staging_dir,
                dataset_id=_dataset_id(args.datasets_dir),
                settings=settings,
                taxonomy=taxonomy,
                generated_at=datetime.now(UTC).isoformat(timespec="seconds"),
                run_id=run_id,
                repo_root=_REPO_ROOT,
            )

        _freeze_datasets(datasets, out_dir, finalize=finalize)
    return datasets, []


def _dataset_id(datasets_dir: Path) -> str:
    manifest = load_manifest(datasets_dir)
    return manifest.dataset_id if manifest else "seed"


def _freeze_datasets(
    datasets: dict[str, list[Any]],
    out_dir: Path,
    *,
    finalize: Callable[[Path], None] | None = None,
) -> None:
    """把（live 回填后的）数据集写出为 jsonl 副本，供后续离线复现。"""
    if out_dir.exists():
        raise ValueError(f"live 输出目录已存在，拒绝覆盖：{out_dir}")
    out_dir.parent.mkdir(parents=True, exist_ok=True)
    staging_dir = Path(tempfile.mkdtemp(prefix=f".{out_dir.name}.", dir=out_dir.parent))
    try:
        for kind, (filename, _) in DATASET_FILES.items():
            rows = datasets.get(kind) or []
            with (staging_dir / filename).open("w", encoding="utf-8") as fh:
                for row in rows:
                    fh.write(row.model_dump_json(exclude_none=True) + "\n")
        (staging_dir / "README.md").write_text(
            "本目录由 `shijiajing-eval --live --output-datasets-dir` 生成：\n"
            "- recorded 字段为真实适配器在评测时刻的输出（冻结快照）。\n"
            "- 商品数据来源以生成环境为准，不得与真实平台数据混淆。\n",
            encoding="utf-8",
        )
        if finalize is not None:
            finalize(staging_dir)
        staging_dir.replace(out_dir)
    finally:
        if staging_dir.exists():
            shutil.rmtree(staging_dir)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    configure_utf8_output()
    args = _parse_args(argv)
    datasets_dir: Path = args.datasets_dir
    report_dir: Path = args.report_dir

    try:
        _invalidate_report_artifacts(report_dir)
        if args.frozen:
            _invalidate_frozen_report(report_dir)
    except ValueError as exc:
        print(f"配置错误：{exc}", file=sys.stderr)
        return _EXIT_CONFIG_ERROR

    if not datasets_dir.exists():
        print(f"数据集目录不存在：{datasets_dir}", file=sys.stderr)
        return _EXIT_CONFIG_ERROR

    datasets = load_all_datasets(datasets_dir)
    total = sum(len(rows) for rows in datasets.values())
    if total == 0:
        print(f"数据集目录为空：{datasets_dir}", file=sys.stderr)
        return _EXIT_CONFIG_ERROR

    # §10：两个输出参数同时出现时返回配置错误
    if args.output_datasets_dir is not None and args.freeze_dir is not None:
        print("--output-datasets-dir 与 --freeze-dir 不能同时使用", file=sys.stderr)
        return _EXIT_CONFIG_ERROR
    live_output_dir = args.output_datasets_dir or args.freeze_dir
    if args.live and live_output_dir is not None and live_output_dir.exists():
        print(f"配置错误：live 输出目录已存在，拒绝覆盖：{live_output_dir}", file=sys.stderr)
        return _EXIT_CONFIG_ERROR

    manifest = load_manifest(datasets_dir)
    trust_level = manifest.trust_level if manifest else TRUST_LEVEL_PROVISIONAL
    label_method = manifest.label_method if manifest else LABEL_METHOD_AGENT
    gate_eligible = manifest.gate_eligible if manifest else GATE_ELIGIBLE_FALSE

    if args.frozen:
        if manifest is None:
            print("配置错误：frozen 数据集缺少 manifest.json", file=sys.stderr)
            return _EXIT_CONFIG_ERROR
        if (
            trust_level != TRUST_LEVEL_FROZEN
            or label_method != LABEL_METHOD_ADJUDICATED
            or not gate_eligible
        ):
            print(
                "配置错误：数据集必须为 frozen + label_method=adjudicated + gate_eligible=true，"
                "不得生成 frozen_eval_report",
                file=sys.stderr,
            )
            return _EXIT_CONFIG_ERROR
        metadata_errors = validate_frozen_dataset_metadata(datasets_dir, manifest)
        if metadata_errors:
            print(
                f"配置错误：frozen 数据集校验失败（{len(metadata_errors)} 项）",
                file=sys.stderr,
            )
            for error in metadata_errors[:50]:
                print(f"  - {error}", file=sys.stderr)
            return _EXIT_CONFIG_ERROR

    settings = load_settings()
    source = "live" if args.live else "offline"
    pending_reasons: list[str] = []
    if args.live:
        try:
            datasets, pending_reasons = run_async(_run_live(datasets, settings, args))
        except ValueError as exc:
            print(f"live 评测配置错误：{exc}", file=sys.stderr)
            return _EXIT_CONFIG_ERROR
        except Exception as exc:
            print(f"live 评测执行失败：{type(exc).__name__}: {exc}", file=sys.stderr)
            return _EXIT_CONFIG_ERROR

    report: EvalReport = compute_report(
        datasets,
        load_taxonomy(settings.taxonomy_path_resolved),
        source=source,
        generated_at=datetime.now(UTC).isoformat(timespec="seconds"),
        datasets_dir=datasets_dir,
        trust_level=trust_level,
        label_method=label_method,
        gate_eligible=gate_eligible,
        pending_reasons=pending_reasons,
    )

    report_artifacts = {
        "eval_report.json": json.dumps(report_to_json(report), ensure_ascii=False, indent=2),
        "eval_report.md": report_to_markdown(report),
    }
    strategy_samples = cast(list[RetrievalStrategySample], datasets.get("retrieval_strategy", []))
    if strategy_samples:
        strategy_report = evaluate_retrieval_strategies(
            strategy_samples,
            rrf_k=settings.retrieval_rrf_k,
            limit=20,
        )
        report_artifacts.update(
            {
                "retrieval_strategy_comparison.json": json.dumps(
                    strategy_report.model_dump(mode="json"),
                    ensure_ascii=False,
                    indent=2,
                ),
                "retrieval_strategy_comparison.md": retrieval_strategy_report_to_markdown(
                    strategy_report
                ),
            }
        )
    engineering_report = run_async(
        evaluate_engineering_datasets(datasets, load_taxonomy(settings.taxonomy_path_resolved))
    )
    report_artifacts.update(
        {
            "engineering_eval_report.json": json.dumps(
                engineering_report.model_dump(mode="json"),
                ensure_ascii=False,
                indent=2,
            ),
            "engineering_eval_report.md": engineering_report_to_markdown(engineering_report),
        }
    )
    try:
        _commit_report_artifacts(report_dir, report_artifacts)
    except ValueError as exc:
        print(f"评测报告写入失败：{exc}", file=sys.stderr)
        return _EXIT_CONFIG_ERROR
    print(f"评测报告：{report_dir / 'eval_report.md'}（数据来源：{source}）")
    print(
        f"可信等级：{trust_level}；发布门禁资格：{'✅' if report.release_gate_eligible else '❌'}"
    )

    if report.metric_gate_passed:
        print("✅ 已测阻断指标全部达标")
    else:
        print("❌ 存在阻断指标未达标")
        for m in report.blocking_failures:
            threshold = m.threshold
            if threshold is None or m.value is None:  # 属性保证，窄化防御
                continue
            print(f"  - {m.name}: {m.value:g}（要求 {threshold.op} {threshold.value:g}）")
        for m in report.blocking_pending:
            print(f"  - {m.name}: 未测量（需 live 数据）")
    for reason in pending_reasons:
        print(f"  - 缺失配置：{reason}")

    if args.frozen:
        # §11：provisional 使用 --frozen 返回配置错误 2，不写 frozen report
        if (
            trust_level != TRUST_LEVEL_FROZEN
            or label_method != LABEL_METHOD_ADJUDICATED
            or not gate_eligible
        ):
            print(
                "配置错误：数据集必须为 frozen + label_method=adjudicated + gate_eligible=true，"
                "不得生成 frozen_eval_report",
                file=sys.stderr,
            )
            return _EXIT_CONFIG_ERROR
        if gate_check(report) and report.release_gate_eligible:
            try:
                frozen = _write_frozen_report(report_dir, report)
            except ValueError as exc:
                print(f"配置错误：{exc}", file=sys.stderr)
                return _EXIT_CONFIG_ERROR
            print(f"冻结报告已写入：{frozen}")

    if args.no_gate:
        return _EXIT_PASS
    if (
        trust_level != TRUST_LEVEL_FROZEN
        or label_method != LABEL_METHOD_ADJUDICATED
        or not gate_eligible
    ):
        # §11：provisional 数据默认退出码为 1，明确打印不可作为发布门禁
        print(
            "⚠️  数据集不具备发布门禁资格（需 frozen + label_method=adjudicated + "
            "gate_eligible=true）"
        )
        return _EXIT_GATE_FAIL
    return _EXIT_PASS if gate_check(report) else _EXIT_GATE_FAIL


if __name__ == "__main__":
    sys.exit(main())
