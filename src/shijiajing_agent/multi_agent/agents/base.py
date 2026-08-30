"""Specialist Agent 执行器协议与统一结果构造。"""

from __future__ import annotations

from time import perf_counter
from typing import Protocol

from shijiajing_agent.contracts import (
    AgentResultV2,
    AgentTaskError,
    AgentTaskOutput,
    AgentTaskUsage,
    AgentTaskV2,
    MemoryMutation,
    NodeStatus,
    SpecialistAgentName,
    content_hash,
)


class SpecialistAgent(Protocol):
    name: SpecialistAgentName

    async def execute(self, task: AgentTaskV2) -> AgentResultV2: ...


def task_usage(start: float, *, calls: int = 0, fallback: bool = False) -> AgentTaskUsage:
    """构造所有 Specialist Agent 共用的任务用量。"""
    return AgentTaskUsage(
        model_calls=calls,
        duration_ms=max(0.0, (perf_counter() - start) * 1000),
        retry_count=1 if fallback else 0,
    )


def result_for(
    task: AgentTaskV2,
    *,
    status: NodeStatus,
    output: AgentTaskOutput | None = None,
    error: AgentTaskError | None = None,
    evidence_refs: list[str] | None = None,
    proposed_memory_mutations: list[MemoryMutation] | None = None,
    usage: AgentTaskUsage | None = None,
) -> AgentResultV2:
    payload = (
        output.model_dump(mode="json")
        if output is not None
        else {
            "error": error.model_dump(mode="json") if error else None,
        }
    )
    mutations = proposed_memory_mutations or []
    return AgentResultV2(
        plan_id=task.plan_id,
        task_id=task.task_id,
        agent_name=task.agent_name,
        task_kind=task.task_kind,
        status=status,
        output=output,
        error=error,
        evidence_refs=evidence_refs or [],
        proposed_memory_mutations=mutations,
        usage=usage or AgentTaskUsage(),
        output_hash=content_hash(payload),
    )


def fixed_error(code: str, message: str, *, retryable: bool = False) -> AgentTaskError:
    return AgentTaskError(code=code, message=message, retryable=retryable)
