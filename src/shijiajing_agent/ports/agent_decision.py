"""主 Agent 决策与可选商品详情端口。"""

from __future__ import annotations

from typing import Protocol

from shijiajing_agent.agent_runtime.contracts import (
    ActionKind,
    DecisionObservation,
    DecisionResult,
    SubagentActionKind,
    SubagentDecisionResult,
    SubagentObservation,
)
from shijiajing_agent.contracts import Offer


class AgentDecisionPort(Protocol):
    """根据观察选择一个受限动作；适配器不得写共享 runtime 状态。"""

    async def decide(
        self,
        observation: DecisionObservation,
        allowed_actions: tuple[ActionKind, ...],
    ) -> DecisionResult: ...


class OfferDetailPort(Protocol):
    """可选的补充商品详情证据能力。没有实现时不得向模型开放。"""

    async def get_details(self, offer_ids: list[str], fields: list[str]) -> list[Offer]: ...


class SubagentDecisionPort(Protocol):
    """子 Agent 决策端口；它只能在自己的有限动作目录中选择。"""

    async def decide(
        self,
        observation: SubagentObservation,
        allowed_actions: tuple[SubagentActionKind, ...],
    ) -> SubagentDecisionResult: ...


__all__ = ["AgentDecisionPort", "OfferDetailPort", "SubagentDecisionPort"]
