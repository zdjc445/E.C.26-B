"""LangGraph dynamic dispatch 边界。

实际 legacy graph 仍由 `graph.py` 维护；此模块把 2.0 plan 转换为 LangGraph `Send`，供
Supervisor graph 迁移时直接复用，并集中保证 ready-task barrier 语义。
"""

from __future__ import annotations

from collections.abc import Mapping

from langgraph.types import Send

from shijiajing_agent.contracts import (
    AgentResultV2,
    AgentTaskV2,
    ExecutionPlan,
    SpecialistAgentName,
)


def find_ready_tasks(
    plan: ExecutionPlan,
    task_results: Mapping[str, AgentResultV2],
) -> list[AgentTaskV2]:
    """只返回所有依赖均有终态结果的任务；不会根据拓扑猜测 Barrier 已完成。"""
    return [
        task
        for task in plan.tasks
        if task.task_id not in task_results
        and all(parent in task_results for parent in task.depends_on)
    ]


def dispatch_ready_tasks(
    plan: ExecutionPlan,
    task_results: Mapping[str, AgentResultV2],
    *,
    agent_nodes: Mapping[SpecialistAgentName, str] | None = None,
) -> list[Send]:
    nodes = agent_nodes or {name: f"agent_{name.value}" for name in SpecialistAgentName}
    return [
        Send(nodes[task.agent_name], {"task": task})
        for task in find_ready_tasks(plan, task_results)
    ]
