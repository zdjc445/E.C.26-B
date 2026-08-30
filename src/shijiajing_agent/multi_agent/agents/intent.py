"""Intent Agent：购物意图抽取与受控规则降级。"""

from __future__ import annotations

from time import perf_counter
from typing import TypedDict

from shijiajing_agent.contracts import (
    AgentResultV2,
    AgentTaskError,
    AgentTaskUsage,
    AgentTaskV2,
    IntentPatch,
    IntentTaskInput,
    IntentTaskOutput,
    NodeStatus,
    SpecialistAgentName,
)
from shijiajing_agent.domain.intent_rules import RuleIntentParser
from shijiajing_agent.domain.memory_policy import validate_memory_directives
from shijiajing_agent.multi_agent.agents.base import fixed_error, result_for, task_usage
from shijiajing_agent.ports.dependencies import AgentDependenciesPort


class IntentAgentState(TypedDict, total=False):
    task_id: str
    text_length: int
    repair_count: int
    patch: IntentPatch | None
    error: AgentTaskError | None
    usage: AgentTaskUsage


class IntentAgent:
    name = SpecialistAgentName.INTENT

    def __init__(self, deps: AgentDependenciesPort) -> None:
        self._deps = deps

    async def execute(self, task: AgentTaskV2) -> AgentResultV2:
        start = perf_counter()
        data = task.input
        if not isinstance(data, IntentTaskInput):
            return result_for(
                task,
                status=NodeStatus.FAILED,
                error=fixed_error("INVALID_TASK_INPUT", "Intent input 类型不匹配"),
            )
        if not data.text:
            return result_for(task, status=NodeStatus.SUCCESS, output=IntentTaskOutput(patch=None))
        try:
            try:
                patch = await self._deps.intent.extract_intent(
                    data.text,
                    data.previous_constraints,
                    self._deps.taxonomy,
                    recent_turns=data.recent_turns,
                )
            except TypeError:
                patch = await self._deps.intent.extract_intent(
                    data.text, data.previous_constraints, self._deps.taxonomy
                )
            current_category = patch.category_id or (
                data.previous_constraints.category_id.value
                if data.previous_constraints is not None
                else None
            )
            patch = patch.model_copy(
                update={
                    "memory_directives": validate_memory_directives(
                        list(patch.memory_directives),
                        text=data.text,
                        taxonomy=self._deps.taxonomy,
                        current_category_id=current_category,
                    )
                }
            )
            return result_for(
                task,
                status=NodeStatus.SUCCESS,
                output=IntentTaskOutput(patch=patch),
                usage=task_usage(start, calls=1),
            )
        except Exception:
            patch = RuleIntentParser(self._deps.taxonomy).parse(data.text)
            return result_for(
                task,
                status=NodeStatus.FALLBACK,
                output=IntentTaskOutput(patch=patch),
                error=fixed_error("INTENT_MODEL_UNAVAILABLE", "意图模型不可用，已使用规则解析"),
                usage=task_usage(start, calls=1, fallback=True),
            )


__all__ = ["IntentAgent", "IntentAgentState"]
