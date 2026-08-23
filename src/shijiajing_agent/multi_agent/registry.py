"""Specialist Agent registry。

注册表是 Supervisor 唯一的 dispatch 边界；Agent executor 不持有 registry，也不能从
任务 input 推断另一个 Agent。
"""

from __future__ import annotations

from collections.abc import Mapping

from shijiajing_agent.contracts import AgentResultV2, AgentTaskV2, SpecialistAgentName
from shijiajing_agent.errors import CapabilityDeniedError
from shijiajing_agent.multi_agent.agents.base import SpecialistAgent
from shijiajing_agent.multi_agent.agents.specialists import (
    ExplanationAgent,
    IntentAgent,
    MemoryAgent,
    RecognitionAgent,
    RetrievalAgent,
)


class SpecialistAgentRegistry:
    def __init__(self, agents: Mapping[SpecialistAgentName, SpecialistAgent] | None = None) -> None:
        self._agents: dict[SpecialistAgentName, SpecialistAgent] = dict(agents or {})

    def register(self, agent: SpecialistAgent) -> None:
        name = agent.name
        if name in self._agents:
            raise ValueError(f"Agent 已注册: {name.value}")
        self._agents[name] = agent

    def get(self, name: SpecialistAgentName) -> SpecialistAgent:
        try:
            return self._agents[name]
        except KeyError as exc:
            raise CapabilityDeniedError(f"Agent 未注册: {name.value}") from exc

    def names(self) -> frozenset[SpecialistAgentName]:
        return frozenset(self._agents)

    async def dispatch(self, task: AgentTaskV2) -> AgentResultV2:
        agent = self.get(task.agent_name)
        if agent.name is not task.agent_name:
            raise CapabilityDeniedError("registry dispatch 的 Agent 身份不匹配")
        return await agent.execute(task)


def build_registry(deps: object) -> SpecialistAgentRegistry:
    typed_deps = deps  # 由构造器内部按端口协议使用，避免依赖 facade 的具体类。
    return SpecialistAgentRegistry(
        {
            SpecialistAgentName.RECOGNITION: RecognitionAgent(typed_deps),  # type: ignore[arg-type]
            SpecialistAgentName.INTENT: IntentAgent(typed_deps),  # type: ignore[arg-type]
            SpecialistAgentName.RETRIEVAL: RetrievalAgent(typed_deps),  # type: ignore[arg-type]
            SpecialistAgentName.EXPLANATION: ExplanationAgent(typed_deps),  # type: ignore[arg-type]
            SpecialistAgentName.MEMORY: MemoryAgent(typed_deps),  # type: ignore[arg-type]
        }
    )
