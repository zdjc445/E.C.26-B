"""主 Agent 决策薄封装。"""

from __future__ import annotations

from shijiajing_agent.agent_runtime.contracts import (
    ActionKind,
    DecisionObservation,
    DecisionResult,
)
from shijiajing_agent.agent_runtime.policy import ActionRejectedError
from shijiajing_agent.ports.agent_decision import AgentDecisionPort


class MainAgent:
    def __init__(self, decision_port: AgentDecisionPort) -> None:
        self._decision_port = decision_port

    async def decide(
        self,
        observation: DecisionObservation,
        allowed_actions: tuple[ActionKind, ...],
    ) -> DecisionResult:
        result = await self._decision_port.decide(observation, allowed_actions)
        if result.action.kind not in allowed_actions:
            raise ActionRejectedError(f"模型返回了未授权动作: {result.action.kind.value}")
        return result


__all__ = ["MainAgent"]
