"""Memory Agent：长期记忆召回、变更准备与受控提交。"""

from __future__ import annotations

from time import perf_counter
from typing import TypedDict

from shijiajing_agent.contracts import (
    AgentResultV2,
    AgentTaskError,
    AgentTaskUsage,
    AgentTaskV2,
    MemoryMutation,
    MemoryRecord,
    MemoryTaskInput,
    MemoryTaskOutput,
    NodeStatus,
    SpecialistAgentName,
    content_hash,
)
from shijiajing_agent.domain.memory_policy import (
    build_memory_mutation,
    memory_authorization_id,
    validate_directive,
)
from shijiajing_agent.errors import CapabilityDeniedError
from shijiajing_agent.multi_agent.agents.base import fixed_error, result_for, task_usage
from shijiajing_agent.ports.dependencies import AgentDependenciesPort


class MemoryAgentState(TypedDict, total=False):
    task_id: str
    operation: str
    records: list[MemoryRecord]
    mutations: list[MemoryMutation]
    committed: bool
    error: AgentTaskError | None
    usage: AgentTaskUsage


class MemoryAgent:
    name = SpecialistAgentName.MEMORY

    def __init__(self, deps: AgentDependenciesPort) -> None:
        self._deps = deps
        self._committed_mutation_ids: set[str] = set()

    async def execute(self, task: AgentTaskV2) -> AgentResultV2:
        start = perf_counter()
        data = task.input
        if not isinstance(data, MemoryTaskInput):
            return result_for(
                task,
                status=NodeStatus.FAILED,
                error=fixed_error("INVALID_TASK_INPUT", "Memory input 类型不匹配"),
            )
        if not data.memory_owner_id or self._deps.memory is None:
            return result_for(
                task,
                status=NodeStatus.FALLBACK,
                output=MemoryTaskOutput(operation=data.operation),
                error=fixed_error("MEMORY_UNAVAILABLE", "长期记忆不可用，本轮不阻断业务"),
            )
        try:
            if data.operation == "recall":
                if data.query is None:
                    raise ValueError("memory.recall 必须由 Supervisor 提供当前品类 MemoryQuery")
                query = data.query
                records = await self._deps.memory.recall(data.memory_owner_id, query)
                return result_for(
                    task,
                    status=NodeStatus.SUCCESS,
                    output=MemoryTaskOutput(operation="recall", records=records),
                    usage=task_usage(start),
                )
            if data.operation == "prepare":
                if not data.session_id or not data.request_id:
                    raise ValueError("memory.prepare 缺少 session_id/request_id")
                mutations: list[MemoryMutation] = []
                for index, item in enumerate(data.directives):
                    try:
                        mutations.append(
                            build_memory_mutation(
                                data.memory_owner_id,
                                data.session_id,
                                data.request_id,
                                index,
                                validate_directive(item, self._deps.taxonomy),
                            )
                        )
                    except Exception:
                        continue
                return result_for(
                    task,
                    status=NodeStatus.SUCCESS,
                    output=MemoryTaskOutput(operation="prepare", mutations=mutations),
                    proposed_memory_mutations=mutations,
                    usage=task_usage(start),
                )
            if not data.authorization_id or not data.authorization_interrupt_id:
                raise CapabilityDeniedError("Memory commit 必须携带 Supervisor 授权")
            expected_payload_hashes = {
                item.mutation_id: content_hash(item.model_dump(mode="json"))
                for item in data.mutations
            }
            if (
                data.authorization_id
                != memory_authorization_id(data.authorization_interrupt_id, data.mutations)
                or data.authorization_mutation_ids != [item.mutation_id for item in data.mutations]
                or data.authorization_payload_hashes != expected_payload_hashes
            ):
                raise CapabilityDeniedError("Memory commit 授权与当前 mutations 不匹配")
            pending = [
                mutation
                for mutation in data.mutations
                if mutation.mutation_id not in self._committed_mutation_ids
            ]
            if not pending:
                return result_for(
                    task,
                    status=NodeStatus.SUCCESS,
                    output=MemoryTaskOutput(
                        operation="commit",
                        mutations=data.mutations,
                        committed=True,
                        saved=True,
                    ),
                    usage=task_usage(start),
                )
            records = await self._deps.memory.commit(data.memory_owner_id, pending)
            self._committed_mutation_ids.update(item.mutation_id for item in pending)
            return result_for(
                task,
                status=NodeStatus.SUCCESS,
                output=MemoryTaskOutput(
                    operation="commit",
                    records=records,
                    mutations=pending,
                    committed=True,
                    saved=True,
                ),
                usage=task_usage(start),
            )
        except CapabilityDeniedError:
            return result_for(
                task,
                status=NodeStatus.FAILED,
                error=fixed_error("CAPABILITY_DENIED", "Memory commit 未获 Supervisor 授权"),
                usage=task_usage(start),
            )
        except Exception:
            return result_for(
                task,
                status=NodeStatus.FAILED if data.operation == "commit" else NodeStatus.FALLBACK,
                output=(
                    None
                    if data.operation == "commit"
                    else MemoryTaskOutput(operation=data.operation)
                ),
                error=fixed_error("MEMORY_OPERATION_FAILED", "记忆操作失败，结果未伪装为已保存"),
                usage=task_usage(start),
            )


__all__ = ["MemoryAgent", "MemoryAgentState"]
