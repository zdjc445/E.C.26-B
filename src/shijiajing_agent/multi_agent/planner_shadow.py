"""模型 Planner 的只读 shadow 证据与报告校验。"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, cast

from shijiajing_agent.multi_agent.planner_contracts import PlanningOutcome

PLANNER_SHADOW_REPORT_SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class PlannerShadowEvidence:
    data_version: str
    model_version: str
    sample_count: int
    plan_difference_count: int
    latency_ms_p50: float
    latency_ms_p95: float
    token_total: int
    fallback_count: int
    invariant_violation_count: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "data_version": self.data_version,
            "model_version": self.model_version,
            "sample_count": self.sample_count,
            "plan_difference_count": self.plan_difference_count,
            "latency_ms_p50": self.latency_ms_p50,
            "latency_ms_p95": self.latency_ms_p95,
            "token_total": self.token_total,
            "fallback_count": self.fallback_count,
            "invariant_violation_count": self.invariant_violation_count,
        }


def build_planner_shadow_evidence(
    outcomes: Sequence[PlanningOutcome],
    plan_differences: Sequence[bool],
    *,
    data_version: str,
    model_version: str,
    invariant_violation_count: int = 0,
) -> PlannerShadowEvidence:
    if not outcomes or len(outcomes) != len(plan_differences):
        raise ValueError("Planner shadow outcomes 与 plan_differences 数量必须一致且非空")
    durations = sorted(float(item.duration_ms) for item in outcomes)
    return PlannerShadowEvidence(
        data_version=data_version,
        model_version=model_version,
        sample_count=len(outcomes),
        plan_difference_count=sum(plan_differences),
        latency_ms_p50=_percentile(durations, 0.50),
        latency_ms_p95=_percentile(durations, 0.95),
        token_total=sum(int(item.token_usage.get("total_tokens", 0)) for item in outcomes),
        fallback_count=sum(item.fallback_reason is not None for item in outcomes),
        invariant_violation_count=invariant_violation_count,
    )


def validate_planner_shadow_report_payload(payload: Mapping[str, Any]) -> str | None:
    """重新计算关键派生值，不直接信任报告中的 gate 字段。"""
    required = {
        "schema_version",
        "mode",
        "case_count",
        "preserved_count",
        "preserved_rate",
        "side_effects_blocked",
        "gate_passed",
        "cases",
        "planner",
    }
    if set(payload) != required:
        return "Planner shadow 报告字段集合无效"
    if payload["schema_version"] != PLANNER_SHADOW_REPORT_SCHEMA_VERSION:
        return "Planner shadow 报告 schema_version 无效"
    if payload["mode"] != "planner_shadow":
        return "Planner shadow 报告 mode 无效"
    raw_cases = payload["cases"]
    if not isinstance(raw_cases, list) or not raw_cases:
        return "Planner shadow 报告 cases 不能为空"
    cases = cast(list[Any], raw_cases)
    if payload["case_count"] != len(cases):
        return "Planner shadow 报告 case_count 不一致"
    preserved_count = payload["preserved_count"]
    if not isinstance(preserved_count, int) or isinstance(preserved_count, bool):
        return "Planner shadow 报告 preserved_count 无效"
    if not 0 <= preserved_count <= len(cases):
        return "Planner shadow 报告 preserved_count 无效"
    rate = payload["preserved_rate"]
    if not _is_nonnegative_number(rate) or float(rate) > 1:
        return "Planner shadow 报告 preserved_rate 无效"
    if round(preserved_count / len(cases), 6) != round(float(rate), 6):
        return "Planner shadow 报告 preserved_rate 不一致"
    if payload["side_effects_blocked"] is not True or payload["gate_passed"] is not True:
        return "Planner shadow 报告门禁未通过"

    outcomes: list[Mapping[str, Any]] = []
    plan_difference_count = 0
    for raw_case in cases:
        if not isinstance(raw_case, Mapping):
            return "Planner shadow case 结构无效"
        case = cast(Mapping[str, Any], raw_case)
        if (
            not isinstance(case.get("case_id"), str)
            or case.get("execution_plan_preserved") is not True
            or case.get("side_effects_blocked") is not True
            or case.get("differences") != []
        ):
            return "Planner shadow 存在执行基线变化或副作用未隔离的 case"
        baseline = case.get("baseline_signature")
        executed = case.get("executed_signature")
        outcome = case.get("planner_outcome")
        if not all(isinstance(item, Mapping) for item in (baseline, executed, outcome)):
            return "Planner shadow case 缺少签名或 Planner outcome"
        baseline_map = cast(Mapping[str, Any], baseline)
        executed_map = cast(Mapping[str, Any], executed)
        outcome_map = cast(Mapping[str, Any], outcome)
        plan_hash = outcome_map.get("plan_hash")
        if (
            outcome_map.get("model_attempted") is not True
            or outcome_map.get("source") != "deterministic"
            or not isinstance(outcome_map.get("validated"), bool)
            or outcome_map.get("accepted") is not False
            or not _is_sha256(plan_hash)
            or baseline_map.get("plan_hash") != plan_hash
            or executed_map.get("plan_hash") != plan_hash
        ):
            return "Planner shadow outcome 或执行计划哈希无效"
        candidate_hash = outcome_map.get("candidate_plan_hash")
        if candidate_hash is not None and not _is_sha256(candidate_hash):
            return "Planner shadow candidate_plan_hash 无效"
        if candidate_hash is not None and candidate_hash != plan_hash:
            plan_difference_count += 1
        if not _is_nonnegative_number(outcome_map.get("duration_ms")):
            return "Planner shadow duration_ms 无效"
        raw_token_usage = outcome_map.get("token_usage")
        if not isinstance(raw_token_usage, Mapping):
            return "Planner shadow token_usage 无效"
        token_usage = cast(Mapping[str, Any], raw_token_usage)
        token_total = token_usage.get("total_tokens")
        if not isinstance(token_total, int) or isinstance(token_total, bool) or token_total < 0:
            return "Planner shadow token_usage 无效"
        outcomes.append(outcome_map)

    if preserved_count != len(cases):
        return "Planner shadow preserved_count 与 cases 不一致"
    raw_planner = payload["planner"]
    if not isinstance(raw_planner, Mapping):
        return "Planner shadow planner 证据结构无效"
    planner = cast(Mapping[str, Any], raw_planner)
    expected_fields = {
        "data_version",
        "model_version",
        "sample_count",
        "plan_difference_count",
        "latency_ms_p50",
        "latency_ms_p95",
        "token_total",
        "fallback_count",
        "invariant_violation_count",
    }
    if set(planner) != expected_fields:
        return "Planner shadow planner 证据字段集合无效"
    if (
        planner["sample_count"] != len(cases)
        or planner["plan_difference_count"] != plan_difference_count
        or planner["invariant_violation_count"] != 0
        or planner["fallback_count"]
        != sum(outcome.get("fallback_reason") is not None for outcome in outcomes)
        or planner["token_total"]
        != sum(
            cast(Mapping[str, int], outcome["token_usage"])["total_tokens"] for outcome in outcomes
        )
    ):
        return "Planner shadow planner 聚合计数不一致"
    durations = sorted(float(outcome["duration_ms"]) for outcome in outcomes)
    if planner["latency_ms_p50"] != _percentile(durations, 0.50) or planner[
        "latency_ms_p95"
    ] != _percentile(durations, 0.95):
        return "Planner shadow 延迟分位数不一致"
    return None


def _percentile(values: Sequence[float], fraction: float) -> float:
    if not values or not 0 <= fraction <= 1:
        raise ValueError("percentile 输入无效")
    index = min(len(values) - 1, max(0, math.ceil(len(values) * fraction) - 1))
    return round(float(values[index]), 3)


def _is_nonnegative_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and float(value) >= 0
    )


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )
