"""Supervisor 任务 DAG 的 LangGraph dynamic dispatch 边界。

本模块把类型化任务转换为 LangGraph ``Send``，并集中保证 ready-task barrier 语义。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, Send

from shijiajing_agent.contracts import (
    AgentResultV2,
    AgentTaskV2,
    ExecutionPlan,
    SpecialistAgentName,
)
from shijiajing_agent.state import merge_task_results


class _SendDispatchState(TypedDict, total=False):
    tasks: list[AgentTaskV2]
    task: AgentTaskV2
    task_results: Annotated[dict[str, AgentResultV2], merge_task_results]


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


async def dispatch_tasks_with_send(
    registry: Any,
    tasks: list[AgentTaskV2],
) -> dict[str, AgentResultV2]:
    """通过真实 LangGraph ``Send`` 执行一个 ready barrier。

    每次调用只接收 Supervisor 已经授权的任务批次；Send fan-out 完成后 graph 才汇合，
    下一批任务仍由 Supervisor 根据最新结果决定。Specialist 不获得公共 SupervisorState。
    """

    graph_builder: Any = StateGraph(_SendDispatchState)

    def dispatch_node(state: _SendDispatchState) -> dict[str, Any]:
        del state
        return {}

    def route_tasks(state: _SendDispatchState) -> list[Send]:
        return [Send("execute_task", {"task": task}) for task in state.get("tasks", [])]

    async def execute_task(state: _SendDispatchState) -> Command[str]:
        task = state.get("task")
        if task is None:
            raise ValueError("Send payload 缺少 task")
        try:
            result = await registry.dispatch(task)
        except BaseException:
            from shijiajing_agent.contracts import NodeStatus
            from shijiajing_agent.multi_agent.agents.base import fixed_error, result_for

            result = result_for(
                task,
                status=NodeStatus.FAILED,
                error=fixed_error("AGENT_EXECUTION_FAILED", "Agent 执行失败", retryable=True),
            )
        return Command(goto=END, update={"task_results": result})

    graph_builder.add_node("dispatch_ready", dispatch_node)
    graph_builder.add_node("execute_task", execute_task)
    graph_builder.add_edge(START, "dispatch_ready")
    graph_builder.add_conditional_edges("dispatch_ready", route_tasks)
    graph = graph_builder.compile()
    result = await graph.ainvoke({"tasks": tasks, "task_results": {}})
    return dict(result.get("task_results") or {})
