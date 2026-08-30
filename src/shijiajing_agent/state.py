"""Supervisor 公共状态与幂等 reducer。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Any, TypedDict

from shijiajing_agent.contracts import (
    AgentEventRecord,
    AgentExecutionContext,
    AgentInterrupt,
    AgentRequest,
    AgentResponse,
    AgentResultV2,
    CanonicalUnderstanding,
    ConversationTurnSummary,
    ExecutionPlan,
    SupervisorBudgetUsage,
    TaskRecord,
)
from shijiajing_agent.errors import TaskResultConflictError

if TYPE_CHECKING:
    from shijiajing_agent.multi_agent.planner_contracts import PlanningOutcome


def _merge_history(current: list[Any], update: list[Any]) -> list[Any]:
    """合并 append-only 历史，同时允许新一轮用空列表显式清空。"""
    if not current:
        return list(update)
    if not update:
        return []
    common = 0
    limit = min(len(current), len(update))
    while common < limit and current[common] == update[common]:
        common += 1
    if common == len(current):
        return list(update)
    if common == len(update):
        return list(current)
    return [*current, *update[common:]]


def merge_task_results(
    current: dict[str, AgentResultV2] | None,
    update: dict[str, AgentResultV2] | AgentResultV2,
) -> dict[str, AgentResultV2]:
    """同 hash 的任务重放保持幂等，不同 hash 拒绝静默覆盖。"""
    merged = dict(current or {})
    incoming = {update.task_id: update} if isinstance(update, AgentResultV2) else update
    for task_id, result in incoming.items():
        existing = merged.get(task_id)
        if existing is None:
            merged[task_id] = result
            continue
        if existing.output_hash != result.output_hash:
            raise TaskResultConflictError(f"task_id={task_id} 已存在不同 output_hash")
    return merged


class SupervisorState(TypedDict, total=False):
    """Multi-Agent 公共规范状态；Specialist 不接收此类型。"""

    schema_version: str
    session_id: str
    request_id: str
    turn_id: str
    trace_id: str
    current_request: AgentRequest
    execution_context: AgentExecutionContext
    plan: ExecutionPlan
    planning_outcome: PlanningOutcome | None
    planning_outcomes: list[PlanningOutcome]
    task_records: dict[str, TaskRecord]
    task_results: Annotated[dict[str, AgentResultV2], merge_task_results]
    canonical_understanding: CanonicalUnderstanding
    recent_turns: list[ConversationTurnSummary]
    active_interrupt: AgentInterrupt | None
    final_response: AgentResponse | None
    replan_count: int
    total_task_count: int
    budget_usage: SupervisorBudgetUsage
    notices: Annotated[list[str], _merge_history]
    events: Annotated[list[AgentEventRecord], _merge_history]
