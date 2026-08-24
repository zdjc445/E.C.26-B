"""运行真实模型 Planner shadow 样本并生成脱敏发布证据。"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, cast

from shijiajing_agent.adapters.ark_models import ArkModelClient
from shijiajing_agent.adapters.ark_supervisor_planner import ArkSupervisorPlanner
from shijiajing_agent.asyncio_compat import run as run_async
from shijiajing_agent.config import Settings, load_settings
from shijiajing_agent.contracts import AgentRequest, ExecutionPlan, SupervisorPlanningInput
from shijiajing_agent.domain.taxonomy import load_taxonomy
from shijiajing_agent.multi_agent.planner import (
    DeterministicPlanner,
    GuardedSupervisorPlanner,
    PlanValidator,
    plan_hash,
)
from shijiajing_agent.multi_agent.planner_contracts import PlanningOutcome
from shijiajing_agent.multi_agent.shadow import (
    SHADOW_REPORT_SCHEMA_VERSION,
    build_planner_shadow_evidence,
    validate_shadow_report_payload,
)
from shijiajing_agent.tools.cli_support import configure_utf8_output, public_error_message


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="shijiajing-planner-shadow")
    parser.add_argument("--dataset", type=Path, required=True, help="Planner shadow JSONL")
    parser.add_argument("--output", type=Path, required=True, help="新建的脱敏 JSON 报告")
    parser.add_argument("--data-version", help="数据版本；默认使用数据文件 SHA-256")
    parser.add_argument("--max-cases", type=int, help="最多运行的样本数")
    return parser.parse_args(argv)


def _load_cases(path: Path, *, max_cases: int | None = None) -> list[tuple[str, AgentRequest]]:
    if max_cases is not None and max_cases < 1:
        raise ValueError("--max-cases 必须大于 0")
    if not path.is_file():
        raise ValueError(f"Planner shadow 数据集不存在：{path}")
    cases: list[tuple[str, AgentRequest]] = []
    seen: set[str] = set()
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw_line.strip():
            continue
        try:
            raw_payload: Any = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Planner shadow 第 {line_number} 行不是合法 JSON") from exc
        if not isinstance(raw_payload, dict):
            raise ValueError(f"Planner shadow 第 {line_number} 行必须是 JSON 对象")
        payload = cast(dict[str, Any], raw_payload)
        case_id = payload.get("id") or payload.get("case_id")
        request_payload = payload.get("request")
        if isinstance(request_payload, dict):
            request_map = cast(dict[str, Any], request_payload)
            text = request_map.get("text")
            selected_option_id = request_map.get("selected_option_id")
        else:
            subgraph_input = payload.get("subgraph_input")
            nested = (
                cast(dict[str, Any], subgraph_input)
                if isinstance(subgraph_input, dict)
                else {}
            )
            text = payload.get("text") or nested.get("text")
            selected_option_id = payload.get("selected_option_id") or nested.get(
                "selected_option_id"
            )
        if not isinstance(case_id, str) or not case_id or case_id in seen:
            raise ValueError(f"Planner shadow 第 {line_number} 行 id 缺失或重复")
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"Planner shadow 第 {line_number} 行缺少非空 text")
        seen.add(case_id)
        cases.append(
            (
                case_id,
                AgentRequest(
                    session_id="planner-shadow",
                    request_id=case_id,
                    text=text,
                    selected_option_id=(
                        selected_option_id if isinstance(selected_option_id, str) else None
                    ),
                ),
            )
        )
        if max_cases is not None and len(cases) >= max_cases:
            break
    if not cases:
        raise ValueError("Planner shadow 数据集不能为空")
    return cases


def _plan_signature(plan: ExecutionPlan) -> dict[str, Any]:
    return {
        "plan_hash": plan_hash(plan),
        "task_count": len(plan.tasks),
        "task_kinds": [task.task_kind.value for task in plan.tasks],
    }


def _outcome_evidence(outcome: PlanningOutcome) -> dict[str, Any]:
    """只导出审计元数据；禁止写入请求文本、Prompt、任务输入或模型原始响应。"""
    return {
        "source": outcome.source,
        "model_attempted": outcome.model_attempted,
        "validated": outcome.validated,
        "accepted": outcome.accepted,
        "fallback_reason": outcome.fallback_reason,
        "model": outcome.model,
        "prompt_version": outcome.prompt_version,
        "repair_count": outcome.repair_count,
        "duration_ms": round(outcome.duration_ms, 3),
        "proposal_hash": outcome.proposal_hash,
        "candidate_plan_hash": outcome.candidate_plan_hash,
        "plan_hash": outcome.plan_hash,
        "token_usage": dict(outcome.token_usage),
        "action_count": outcome.action_count,
        "task_count": outcome.task_count,
    }


async def build_planner_shadow_report(
    cases: list[tuple[str, AgentRequest]],
    *,
    settings: Settings,
    candidate: Any,
    data_version: str,
) -> dict[str, Any]:
    deterministic = DeterministicPlanner(
        max_tasks=settings.max_agent_tasks,
        max_replans=settings.max_supervisor_replans,
    )
    guarded = GuardedSupervisorPlanner(deterministic, candidate, mode="shadow")
    outcomes: list[PlanningOutcome] = []
    plan_differences: list[bool] = []
    report_cases: list[dict[str, Any]] = []
    invariant_violations = 0

    for case_id, request in cases:
        baseline = deterministic.create_plan(
            request,
            taxonomy_version=settings.taxonomy_path_resolved.stem,
        )
        returned = await guarded.create_plan(
            SupervisorPlanningInput(
                request=request,
                taxonomy_version=settings.taxonomy_path_resolved.stem,
                base_plan=baseline,
            )
        )
        outcome = guarded.last_outcome
        if outcome is None:
            raise RuntimeError("Planner shadow 未产生 PlanningOutcome")
        outcomes.append(outcome)

        differences: list[str] = []
        try:
            PlanValidator().validate(returned)
        except Exception:
            differences.append("plan_validation")
        baseline_signature = _plan_signature(baseline)
        returned_signature = _plan_signature(returned)
        if returned_signature != baseline_signature:
            differences.append("shadow_execution_plan")
        if differences:
            invariant_violations += 1
        candidate_hash = outcome.candidate_plan_hash
        plan_differences.append(
            candidate_hash is not None and candidate_hash != plan_hash(baseline)
        )
        report_cases.append(
            {
                "case_id": case_id,
                "equivalent": not differences,
                "legacy_signature": baseline_signature,
                "multi_agent_signature": returned_signature,
                "differences": differences,
                "side_effects_blocked": True,
                "planner_outcome": _outcome_evidence(outcome),
            }
        )

    evidence = build_planner_shadow_evidence(
        outcomes,
        plan_differences,
        data_version=data_version,
        model_version=settings.supervisor_model or "unknown",
        invariant_violation_count=invariant_violations,
    )
    equivalent_count = sum(1 for case in report_cases if case["equivalent"])
    payload: dict[str, Any] = {
        "schema_version": SHADOW_REPORT_SCHEMA_VERSION,
        "mode": "multi_agent_shadow",
        "case_count": len(report_cases),
        "equivalent_count": equivalent_count,
        "equivalent_rate": round(equivalent_count / len(report_cases), 6),
        "side_effects_blocked": True,
        "gate_passed": equivalent_count == len(report_cases) and invariant_violations == 0,
        "cases": report_cases,
        "planner": evidence.as_dict(),
    }
    validation_error = validate_shadow_report_payload(payload)
    if validation_error is not None:
        raise RuntimeError(f"Planner shadow 报告自校验失败：{validation_error}")
    return payload


async def _run(args: argparse.Namespace, settings: Settings) -> dict[str, Any]:
    missing = settings.validate(require_real_adapters=True)
    if missing:
        names = ", ".join(f"SHIJIAJING_{name}" for name in missing)
        raise ValueError(f"缺少必要配置：{names}")
    engineering_errors = settings.validate_engineering()
    if engineering_errors:
        raise ValueError("二期配置错误：" + ", ".join(engineering_errors))
    if settings.supervisor_planner_mode != "shadow":
        raise ValueError("Planner shadow 报告要求 SHIJIAJING_SUPERVISOR_PLANNER_MODE=shadow")
    if args.output.exists():
        raise ValueError(f"Planner shadow 输出已存在，拒绝覆盖：{args.output}")
    cases = _load_cases(args.dataset, max_cases=args.max_cases)
    data_version = args.data_version or (
        "sha256:" + hashlib.sha256(args.dataset.read_bytes()).hexdigest()
    )
    taxonomy = load_taxonomy(settings.taxonomy_path_resolved)
    client = ArkModelClient(settings)
    try:
        candidate = ArkSupervisorPlanner(client, taxonomy, settings)
        payload = await build_planner_shadow_report(
            cases,
            settings=settings,
            candidate=candidate,
            data_version=data_version,
        )
    finally:
        await client.close()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    return payload


def main(argv: list[str] | None = None) -> int:
    configure_utf8_output()
    args = _parse_args(argv)
    try:
        payload = run_async(_run(args, load_settings()))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception as exc:
        print(public_error_message(exc, fallback="Planner shadow 运行失败"), file=sys.stderr)
        return 1
    planner = payload["planner"]
    print(
        "Planner shadow 报告已生成："
        f"{args.output}；样本={planner['sample_count']}；"
        f"计划差异={planner['plan_difference_count']}；回退={planner['fallback_count']}；"
        f"token={planner['token_total']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
