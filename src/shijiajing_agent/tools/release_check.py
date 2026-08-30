"""生产发布证据门禁 CLI。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from shijiajing_agent.release_gate import (
    PRODUCTION_EVIDENCE_CHECKS,
    build_production_evidence_manifest,
    evaluate_release_gate,
)
from shijiajing_agent.tools.cli_support import configure_utf8_output


def _check_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="shijiajing-release-check")
    parser.add_argument("--verification-summary", type=Path)
    parser.add_argument("--backup-summary", type=Path)
    parser.add_argument("--eval-report", type=Path)
    parser.add_argument("--benchmark-report", type=Path)
    parser.add_argument("--planner-shadow-report", type=Path)
    parser.add_argument("--production-evidence-manifest", type=Path)
    parser.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    return parser.parse_args(argv)


def _manifest_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="shijiajing-release-check create-manifest")
    parser.add_argument("--output", type=Path, required=True)
    for check_id in PRODUCTION_EVIDENCE_CHECKS:
        parser.add_argument(f"--{check_id.replace('_', '-')}", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    configure_utf8_output()
    actual_argv = list(sys.argv[1:] if argv is None else argv)
    if actual_argv and actual_argv[0] == "create-manifest":
        args = _manifest_args(actual_argv[1:])
        try:
            evidence_paths = {
                check_id: getattr(args, check_id) for check_id in PRODUCTION_EVIDENCE_CHECKS
            }
            build_production_evidence_manifest(args.output, evidence_paths)
        except ValueError as exc:
            print(f"生产证据 manifest 生成失败：{exc}", file=sys.stderr)
            return 2
        print(f"生产证据 manifest：{args.output}")
        return 0

    args = _check_args(actual_argv)
    report = evaluate_release_gate(
        verification_summary=args.verification_summary,
        backup_summary=args.backup_summary,
        eval_report=args.eval_report,
        benchmark_report=args.benchmark_report,
        planner_shadow_report=args.planner_shadow_report,
        production_evidence_manifest=args.production_evidence_manifest,
    )
    if args.json:
        print(json.dumps(report.as_dict(), ensure_ascii=False, sort_keys=True))
    else:
        print("发布门禁：" + ("通过" if report.ready else "未就绪"))
        for check in report.checks:
            print(f"- {check.check_id}: {check.status.value}；{check.reason}")
    return 0 if report.ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
