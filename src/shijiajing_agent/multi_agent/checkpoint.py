"""Supervisor/Agent 双层 checkpoint namespace 工具。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Protocol, cast

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver, empty_checkpoint

from shijiajing_agent.contracts import AgentResultV2
from shijiajing_agent.errors import TaskResultConflictError
from shijiajing_agent.state import SupervisorState


def supervisor_checkpoint_namespace(session_id: str, turn_id: str, plan_id: str) -> str:
    return "/".join((session_id, turn_id, plan_id, "supervisor"))


def agent_task_checkpoint_namespace(
    session_id: str,
    turn_id: str,
    plan_id: str,
    task_id: str,
) -> str:
    """稳定层级：session_id / turn_id / plan_id / task_id。"""
    return "/".join((session_id, turn_id, plan_id, task_id))


class MultiAgentCheckpointPort(Protocol):
    """Supervisor plan 与单 task 的双层 checkpoint 抽象。"""

    async def load_supervisor(self, namespace: str) -> tuple[SupervisorState, int] | None: ...

    async def save_supervisor(
        self, namespace: str, state: SupervisorState, expected_version: int | None
    ) -> int: ...

    async def load_task(self, namespace: str) -> AgentResultV2 | None: ...

    async def save_task(self, namespace: str, result: AgentResultV2) -> None: ...


class InMemoryMultiAgentCheckpoint:
    """测试用双层 checkpoint；生产应由 native LangGraph saver 实现同一 namespace 语义。"""

    def __init__(self) -> None:
        self._supervisor: dict[str, tuple[SupervisorState, int]] = {}
        self._tasks: dict[str, AgentResultV2] = {}

    async def load_supervisor(self, namespace: str) -> tuple[SupervisorState, int] | None:
        saved = self._supervisor.get(namespace)
        return (deepcopy(saved[0]), saved[1]) if saved is not None else None

    async def save_supervisor(
        self, namespace: str, state: SupervisorState, expected_version: int | None
    ) -> int:
        current = self._supervisor.get(namespace)
        current_version = current[1] if current is not None else 0
        if expected_version is not None and current_version != expected_version:
            raise ValueError("Supervisor checkpoint version conflict")
        version = current_version + 1
        self._supervisor[namespace] = (deepcopy(state), version)
        return version

    async def load_task(self, namespace: str) -> AgentResultV2 | None:
        result = self._tasks.get(namespace)
        return result.model_copy(deep=True) if result is not None else None

    async def save_task(self, namespace: str, result: AgentResultV2) -> None:
        current = self._tasks.get(namespace)
        if current is not None and current.output_hash != result.output_hash:
            raise ValueError("TASK_RESULT_CONFLICT")
        self._tasks[namespace] = result.model_copy(deep=True)


class LangGraphMultiAgentCheckpoint:
    """把 2.0 的双层 namespace 映射到 LangGraph 原生 saver。

    Supervisor 与每个 task 使用独立的 ``checkpoint_ns``，因此可以在同一个 native
    saver 上分别恢复计划状态和已完成结果。该适配器不绕过 saver 的序列化、脱敏和
    生命周期管理；生产 runtime 仍负责打开并关闭 saver。
    """

    _SUPERVISOR_KEY = "__shijiajing_multi_agent_supervisor__"
    _TASK_KEY = "__shijiajing_multi_agent_task__"

    def __init__(self, saver: BaseCheckpointSaver[str]) -> None:
        self._saver = saver

    @staticmethod
    def _config(namespace: str) -> RunnableConfig:
        return cast(
            RunnableConfig,
            {
                "configurable": {
                    "thread_id": f"multi-agent:{namespace}",
                    "checkpoint_ns": namespace,
                }
            },
        )

    async def _load_value(self, namespace: str, key: str) -> tuple[Any, int] | None:
        item = await self._saver.aget_tuple(self._config(namespace))
        if item is None:
            return None
        raw_values: Any = item.checkpoint.get("channel_values")
        values: dict[str, Any] = (
            cast(dict[str, Any], raw_values) if isinstance(raw_values, dict) else {}
        )
        wrapped = values.get(key)
        if not isinstance(wrapped, dict) or "value" not in wrapped:
            return None
        wrapped_value = cast(dict[str, Any], wrapped)
        raw_version: Any = wrapped_value.get("version", 0)
        version = raw_version if isinstance(raw_version, int) else 0
        return wrapped_value["value"], version

    async def _save_value(self, namespace: str, key: str, value: Any, version: int) -> None:
        checkpoint = empty_checkpoint()
        checkpoint["channel_values"] = {
            key: {
                "value": value,
                "version": version,
            }
        }
        await self._saver.aput(
            self._config(namespace),
            checkpoint,
            {"source": "update", "step": version, "parents": {}},
            {},
        )

    async def load_supervisor(self, namespace: str) -> tuple[SupervisorState, int] | None:
        loaded = await self._load_value(namespace, self._SUPERVISOR_KEY)
        if loaded is None:
            return None
        value, version = loaded
        return cast(SupervisorState, value), version

    async def save_supervisor(
        self, namespace: str, state: SupervisorState, expected_version: int | None
    ) -> int:
        loaded = await self._load_value(namespace, self._SUPERVISOR_KEY)
        current_version = loaded[1] if loaded is not None else 0
        if expected_version is not None and current_version != expected_version:
            raise ValueError("Supervisor checkpoint version conflict")
        version = current_version + 1
        await self._save_value(namespace, self._SUPERVISOR_KEY, state, version)
        return version

    async def load_task(self, namespace: str) -> AgentResultV2 | None:
        loaded = await self._load_value(namespace, self._TASK_KEY)
        if loaded is None:
            return None
        value = loaded[0]
        return value if isinstance(value, AgentResultV2) else AgentResultV2.model_validate(value)

    async def save_task(self, namespace: str, result: AgentResultV2) -> None:
        loaded = await self._load_value(namespace, self._TASK_KEY)
        if loaded is not None:
            current = loaded[0]
            current_result = (
                current
                if isinstance(current, AgentResultV2)
                else AgentResultV2.model_validate(current)
            )
            if current_result.output_hash != result.output_hash:
                raise TaskResultConflictError("native task checkpoint 结果 hash 冲突")
            return
        await self._save_value(namespace, self._TASK_KEY, result, 1)


__all__ = [
    "InMemoryMultiAgentCheckpoint",
    "LangGraphMultiAgentCheckpoint",
    "MultiAgentCheckpointPort",
    "agent_task_checkpoint_namespace",
    "supervisor_checkpoint_namespace",
]
