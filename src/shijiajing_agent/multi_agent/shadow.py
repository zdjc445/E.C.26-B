"""旧 Workflow 与受控 Multi-Agent 的只读灰度对照工具。

灰度比较只比较对外业务不变量，不比较模型措辞、trace 或 turn 标识。
调用方必须提供已经隔离副作用的 runner；本模块不会替 runner 猜测或回滚
外部写入。
"""

from __future__ import annotations

import math
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, cast

from shijiajing_agent.contracts import AgentRequest, AgentResponse
from shijiajing_agent.multi_agent.planner_contracts import PlanningOutcome

SHADOW_REPORT_SCHEMA_VERSION = "1.0"
ShadowRunner = Callable[[AgentRequest], Awaitable[AgentResponse]]


@dataclass(frozen=True)
class PlannerShadowEvidence:
    """模型 Planner shadow 的逐案例聚合证据。"""

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
    """从已脱敏 Planner outcome 和逐案例计划差异生成发布摘要。"""
    if not outcomes or len(outcomes) != len(plan_differences):
        raise ValueError("Planner shadow outcomes 与 plan_differences 数量必须一致且非空")
    durations = sorted(float(item.duration_ms) for item in outcomes)
    tokens = sum(int(item.token_usage.get("total_tokens", 0)) for item in outcomes)
    fallback_count = sum(1 for item in outcomes if item.fallback_reason is not None)
    return PlannerShadowEvidence(
        data_version=data_version,
        model_version=model_version,
        sample_count=len(outcomes),
        plan_difference_count=sum(1 for different in plan_differences if different),
        latency_ms_p50=_percentile(durations, 0.50),
        latency_ms_p95=_percentile(durations, 0.95),
        token_total=tokens,
        fallback_count=fallback_count,
        invariant_violation_count=invariant_violation_count,
    )


def _percentile(values: Sequence[float], fraction: float) -> float:
    if not values or not 0 <= fraction <= 1:
        raise ValueError("percentile 输入无效")
    index = min(len(values) - 1, max(0, math.ceil(len(values) * fraction) - 1))
    return round(float(values[index]), 3)


def _business_signature(response: AgentResponse) -> dict[str, Any]:
    """提取不受模型措辞、trace 和执行时序影响的对外业务字段。"""
    payload = response.model_dump(mode="json")
    constraints: Any = payload["effective_constraints"]
    if isinstance(constraints, dict):
        constraint_map = cast(dict[str, Any], constraints)
        constraints = {
            key: (
                {
                    field: value
                    for field, value in cast(dict[str, Any], item).items()
                    if field != "updated_turn_id"
                }
                if isinstance(item, dict)
                else item
            )
            for key, item in constraint_map.items()
        }
    return {
        "status": payload["status"],
        "recognition": payload["recognition"],
        "effective_constraints": constraints,
        "groups": payload["groups"],
        "clarification": payload["clarification"],
    }


@dataclass(frozen=True)
class ShadowComparison:
    """单个冻结用例的旧图/新图对照结果。"""

    case_id: str
    equivalent: bool
    legacy_signature: Mapping[str, Any]
    multi_agent_signature: Mapping[str, Any]
    differences: tuple[str, ...] = ()
    side_effects_blocked: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "equivalent": self.equivalent,
            "legacy_signature": dict(self.legacy_signature),
            "multi_agent_signature": dict(self.multi_agent_signature),
            "differences": list(self.differences),
            "side_effects_blocked": self.side_effects_blocked,
        }


@dataclass(frozen=True)
class ShadowComparisonReport:
    """可被发布门禁消费的灰度报告。"""

    cases: tuple[ShadowComparison, ...]
    side_effects_blocked: bool = True
    planner_evidence: PlannerShadowEvidence | None = None
    schema_version: str = SHADOW_REPORT_SCHEMA_VERSION

    @property
    def equivalent_count(self) -> int:
        return sum(1 for case in self.cases if case.equivalent)

    @property
    def equivalent_rate(self) -> float:
        return self.equivalent_count / len(self.cases) if self.cases else 0.0

    @property
    def gate_passed(self) -> bool:
        return (
            bool(self.cases)
            and self.side_effects_blocked
            and (
                self.planner_evidence is None
                or self.planner_evidence.invariant_violation_count == 0
            )
            and all(case.equivalent and case.side_effects_blocked for case in self.cases)
        )

    def as_dict(self) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "mode": "multi_agent_shadow",
            "case_count": len(self.cases),
            "equivalent_count": self.equivalent_count,
            "equivalent_rate": round(self.equivalent_rate, 6),
            "side_effects_blocked": self.side_effects_blocked,
            "gate_passed": self.gate_passed,
            "cases": [case.as_dict() for case in self.cases],
        }
        if self.planner_evidence is not None:
            payload["planner"] = self.planner_evidence.as_dict()
        return payload


def compare_responses(
    case_id: str,
    legacy: AgentResponse,
    multi_agent: AgentResponse,
    *,
    side_effects_blocked: bool = True,
) -> ShadowComparison:
    legacy_signature = _business_signature(legacy)
    multi_agent_signature = _business_signature(multi_agent)
    differences = tuple(
        key for key in legacy_signature if legacy_signature[key] != multi_agent_signature[key]
    )
    return ShadowComparison(
        case_id=case_id,
        equivalent=not differences,
        legacy_signature=legacy_signature,
        multi_agent_signature=multi_agent_signature,
        differences=differences,
        side_effects_blocked=side_effects_blocked,
    )


async def run_shadow_case(
    case_id: str,
    request: AgentRequest,
    *,
    legacy_runner: ShadowRunner,
    multi_agent_runner: ShadowRunner,
    side_effects_blocked: bool = True,
) -> ShadowComparison:
    """按固定顺序执行旧图和新图，避免共享 fake/外部端口产生竞态。"""
    legacy = await legacy_runner(request)
    multi_agent = await multi_agent_runner(request)
    return compare_responses(
        case_id,
        legacy,
        multi_agent,
        side_effects_blocked=side_effects_blocked,
    )


async def run_shadow_suite(
    cases: Sequence[tuple[str, AgentRequest]],
    *,
    legacy_runner: ShadowRunner,
    multi_agent_runner: ShadowRunner,
    side_effects_blocked: bool = True,
    planner_evidence: PlannerShadowEvidence | None = None,
) -> ShadowComparisonReport:
    comparisons = [
        await run_shadow_case(
            case_id,
            request,
            legacy_runner=legacy_runner,
            multi_agent_runner=multi_agent_runner,
            side_effects_blocked=side_effects_blocked,
        )
        for case_id, request in cases
    ]
    return ShadowComparisonReport(
        cases=tuple(comparisons),
        side_effects_blocked=side_effects_blocked,
        planner_evidence=planner_evidence,
    )


def validate_shadow_report_payload(payload: Mapping[str, Any]) -> str | None:
    """验证发布门禁使用的 shadow JSON，而不是信任报告中的派生字段。"""
    required = {
        "schema_version",
        "mode",
        "case_count",
        "equivalent_count",
        "equivalent_rate",
        "side_effects_blocked",
        "gate_passed",
        "cases",
    }
    if set(payload) - required - {"planner"} or not required.issubset(payload):
        return "shadow 报告字段集合无效"
    if payload["schema_version"] != SHADOW_REPORT_SCHEMA_VERSION:
        return "shadow 报告 schema_version 无效"
    if payload["mode"] != "multi_agent_shadow":
        return "shadow 报告 mode 无效"
    cases_value = payload["cases"]
    if not isinstance(cases_value, list) or not cases_value:
        return "shadow 报告 cases 不能为空"
    cases = cast(list[Any], cases_value)
    if payload["case_count"] != len(cases):
        return "shadow 报告 case_count 不一致"
    if not isinstance(payload["equivalent_count"], int) or not 0 <= payload[
        "equivalent_count"
    ] <= len(cases):
        return "shadow 报告 equivalent_count 无效"
    rate = payload["equivalent_rate"]
    if not isinstance(rate, (int, float)) or isinstance(rate, bool) or not 0 <= rate <= 1:
        return "shadow 报告 equivalent_rate 无效"
    if round(float(payload["equivalent_count"]) / len(cases), 6) != round(float(rate), 6):
        return "shadow 报告 equivalent_rate 不一致"
    if payload["side_effects_blocked"] is not True:
        return "shadow 报告必须确认 side_effects_blocked"
    if payload["gate_passed"] is not True:
        return "shadow 报告 gate_passed 不为 true"
    for case_value in cases:
        if not isinstance(case_value, Mapping):
            return "shadow 报告 case 结构无效"
        case = cast(Mapping[str, Any], case_value)
        if (
            not isinstance(case.get("case_id"), str)
            or case.get("equivalent") is not True
            or case.get("side_effects_blocked") is not True
            or case.get("differences") != []
        ):
            return "shadow 报告存在未对齐或未隔离副作用的 case"
    if payload["equivalent_count"] != len(cases):
        return "shadow 报告 equivalent_count 与 cases 不一致"
    if "planner" in payload:
        planner = payload["planner"]
        if not isinstance(planner, Mapping):
            return "shadow 报告 planner 证据结构无效"
        planner_map = cast(Mapping[str, Any], planner)
        planner_required = {
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
        if set(planner_map) != planner_required:
            return "shadow 报告 planner 证据字段集合无效"
        if (
            not isinstance(planner_map["data_version"], str)
            or not planner_map["data_version"]
            or not isinstance(planner_map["model_version"], str)
            or not planner_map["model_version"]
            or not isinstance(planner_map["sample_count"], int)
            or planner_map["sample_count"] != len(cases)
            or not isinstance(planner_map["plan_difference_count"], int)
            or not 0 <= planner_map["plan_difference_count"] <= len(cases)
            or not isinstance(planner_map["token_total"], int)
            or planner_map["token_total"] < 0
            or not isinstance(planner_map["fallback_count"], int)
            or not 0 <= planner_map["fallback_count"] <= len(cases)
            or not isinstance(planner_map["invariant_violation_count"], int)
            or planner_map["invariant_violation_count"] < 0
        ):
            return "shadow 报告 planner 证据计数无效"
        for name in ("latency_ms_p50", "latency_ms_p95"):
            value = planner_map[name]
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(float(value))
                or float(value) < 0
            ):
                return "shadow 报告 planner 延迟无效"
        if planner_map["invariant_violation_count"] != 0:
            return "shadow 报告 planner 存在业务不变量违规"
    return None
