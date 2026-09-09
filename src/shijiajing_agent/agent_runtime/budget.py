"""主/子 Agent 共享预算账本。"""

from __future__ import annotations

from dataclasses import dataclass
from time import monotonic

from shijiajing_agent.agent_runtime.contracts import (
    AgentRuntimeUsage,
    RuntimeBudget,
    SubagentBudget,
)


class BudgetExceededError(RuntimeError):
    """动作在执行前无法获得足够的全局预算。"""


@dataclass
class BudgetLedger:
    limits: RuntimeBudget
    usage: AgentRuntimeUsage
    started_at: float

    @classmethod
    def start(cls, limits: RuntimeBudget, usage: AgentRuntimeUsage | None = None) -> BudgetLedger:
        current = usage or AgentRuntimeUsage()
        # ``BudgetLedger`` 在每个边界都会重新创建；把已结算的 elapsed_ms
        # 折算回 started_at，避免每次动作都获得一份新的 max_seconds。
        return cls(limits, current, monotonic() - current.elapsed_ms / 1000.0)

    def can_decide(self) -> bool:
        return self.usage.decisions < self.limits.max_decisions and not self.expired()

    def can_tool(self) -> bool:
        return self.usage.tool_calls < self.limits.max_tool_calls and not self.expired()

    def can_retrieve(self) -> bool:
        return self.usage.retrieval_calls < self.limits.max_retrieval_calls and not self.expired()

    def can_model(self) -> bool:
        return self.usage.model_calls < self.limits.max_model_calls and not self.expired()

    def can_subagent(self) -> bool:
        return self.usage.subagent_starts < self.limits.max_subagent_starts and not self.expired()

    def expired(self) -> bool:
        return monotonic() - self.started_at >= self.limits.max_seconds

    def add(self, usage: AgentRuntimeUsage) -> None:
        next_usage = self.usage.add(usage)
        if next_usage.decisions > self.limits.max_decisions:
            raise BudgetExceededError("主 Agent 决策次数超限")
        if next_usage.tool_calls > self.limits.max_tool_calls:
            raise BudgetExceededError("工具派发次数超限")
        if next_usage.retrieval_calls > self.limits.max_retrieval_calls:
            raise BudgetExceededError("真实检索次数超限")
        if next_usage.db_search_attempts > self.limits.max_db_search_attempts:
            raise BudgetExceededError("数据库检索尝试次数超限")
        if next_usage.embedding_calls > self.limits.max_embedding_calls:
            raise BudgetExceededError("embedding 调用次数超限")
        if next_usage.model_calls > self.limits.max_model_calls:
            raise BudgetExceededError("生成模型调用次数超限")
        if next_usage.subagent_starts > self.limits.max_subagent_starts:
            raise BudgetExceededError("subagent 启动次数超限")
        if next_usage.input_tokens + next_usage.output_tokens > self.limits.max_tokens:
            raise BudgetExceededError("模型 token 预算超限")
        self.usage = next_usage

    def child_budget(self, requested: SubagentBudget) -> SubagentBudget:
        remaining_decisions = max(0, self.limits.max_decisions - self.usage.decisions)
        remaining_tools = max(0, self.limits.max_tool_calls - self.usage.tool_calls)
        remaining_tokens = max(
            1,
            self.limits.max_tokens - self.usage.input_tokens - self.usage.output_tokens,
        )
        remaining_seconds = max(0.001, self.limits.max_seconds - (monotonic() - self.started_at))
        if remaining_decisions < 1 or remaining_tools < 1 or remaining_tokens < 1:
            raise BudgetExceededError("父 Agent 没有足够预算启动 subagent")
        return SubagentBudget(
            max_decisions=min(requested.max_decisions, remaining_decisions),
            max_tool_calls=min(requested.max_tool_calls, remaining_tools),
            max_tokens=min(requested.max_tokens, remaining_tokens),
            max_seconds=min(requested.max_seconds, remaining_seconds),
        )


__all__ = ["BudgetExceededError", "BudgetLedger"]
