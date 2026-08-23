"""旧 Workflow 与受控 Multi-Agent 的只读灰度对照工具。

灰度比较只比较对外业务不变量，不比较模型措辞、trace 或 turn 标识。
调用方必须提供已经隔离副作用的 runner；本模块不会替 runner 猜测或回滚
外部写入。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, cast

from shijiajing_agent.contracts import AgentRequest, AgentResponse

SHADOW_REPORT_SCHEMA_VERSION = "1.0"
ShadowRunner = Callable[[AgentRequest], Awaitable[AgentResponse]]


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
            and all(case.equivalent and case.side_effects_blocked for case in self.cases)
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "mode": "multi_agent_shadow",
            "case_count": len(self.cases),
            "equivalent_count": self.equivalent_count,
            "equivalent_rate": round(self.equivalent_rate, 6),
            "side_effects_blocked": self.side_effects_blocked,
            "gate_passed": self.gate_passed,
            "cases": [case.as_dict() for case in self.cases],
        }


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
    if set(payload) != required:
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
    return None
