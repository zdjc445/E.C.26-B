"""Explanation Agent：基于证据生成并校验比价解释。"""

from __future__ import annotations

from time import perf_counter
from typing import TypedDict

from shijiajing_agent.contracts import (
    AgentResultV2,
    AgentTaskError,
    AgentTaskUsage,
    AgentTaskV2,
    ExplanationTaskInput,
    ExplanationTaskOutput,
    NodeStatus,
    SpecialistAgentName,
)
from shijiajing_agent.domain.evidence import EvidenceBuilder, FactualConsistencyChecker
from shijiajing_agent.multi_agent.agents.base import fixed_error, result_for, task_usage
from shijiajing_agent.ports.dependencies import AgentDependenciesPort


class ExplanationAgentState(TypedDict, total=False):
    task_id: str
    explanation_text: str
    verified: bool
    error: AgentTaskError | None
    usage: AgentTaskUsage


class ExplanationAgent:
    name = SpecialistAgentName.EXPLANATION

    def __init__(self, deps: AgentDependenciesPort) -> None:
        self._deps = deps

    async def execute(self, task: AgentTaskV2) -> AgentResultV2:
        start = perf_counter()
        data = task.input
        if not isinstance(data, ExplanationTaskInput):
            return result_for(
                task,
                status=NodeStatus.FAILED,
                error=fixed_error("INVALID_TASK_INPUT", "Explanation input 类型不匹配"),
            )
        bundle = data.evidence_bundle
        if bundle is None:
            bundle = EvidenceBuilder().build(data.ranked_groups, data.constraints)
        checker = FactualConsistencyChecker()
        try:
            candidate = await self._deps.explanation.explain(bundle)
            verified, _ = checker.verify(candidate, bundle)
            if verified:
                output = ExplanationTaskOutput(
                    explanation_text=candidate,
                    verified=True,
                )
                return result_for(
                    task,
                    status=NodeStatus.SUCCESS,
                    output=output,
                    usage=task_usage(start, calls=1),
                )
        except Exception:
            pass
        output = ExplanationTaskOutput(
            explanation_text=checker.template_explanation(bundle),
            verified=False,
            fallback_reason="factual_check_failed",
        )
        return result_for(
            task,
            status=NodeStatus.FALLBACK,
            output=output,
            error=fixed_error("EXPLANATION_FALLBACK", "解释已降级为确定性模板"),
            usage=task_usage(start, calls=1, fallback=True),
        )


__all__ = ["ExplanationAgent", "ExplanationAgentState"]
