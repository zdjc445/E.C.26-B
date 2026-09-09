"""主 Agent runtime 的可恢复状态与会话快照持久化。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Protocol, cast

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver, empty_checkpoint

from shijiajing_agent.agent_runtime.contracts import (
    MainRuntimeState,
    RuntimeSessionSnapshot,
)
from shijiajing_agent.persistence_safety import sanitize_persisted_value


class AgentRuntimeCheckpointPort(Protocol):
    async def load_request(
        self, session_id: str, request_id: str
    ) -> tuple[MainRuntimeState, int] | None: ...

    async def save_request(
        self,
        state: MainRuntimeState,
        expected_version: int | None,
    ) -> int: ...

    async def load_active(self, session_id: str) -> tuple[str, MainRuntimeState, int] | None: ...

    async def load_session(self, session_id: str) -> RuntimeSessionSnapshot | None: ...

    async def save_session(self, snapshot: RuntimeSessionSnapshot) -> None: ...


def request_namespace(session_id: str, request_id: str) -> str:
    return f"agent-runtime-v1/{session_id}/{request_id}/main"


def session_namespace(session_id: str) -> str:
    return f"agent-runtime-v1/{session_id}/session"


def subagent_namespace(session_id: str, request_id: str, task_id: str) -> str:
    return f"agent-runtime-v1/{session_id}/{request_id}/subagents/{task_id}"


class InMemoryAgentRuntimeCheckpoint:
    """契约测试用实现；保存前也经过持久化脱敏。"""

    def __init__(self) -> None:
        self._requests: dict[str, tuple[MainRuntimeState, int]] = {}
        self._sessions: dict[str, RuntimeSessionSnapshot] = {}
        self._active: dict[str, str] = {}

    async def load_request(
        self, session_id: str, request_id: str
    ) -> tuple[MainRuntimeState, int] | None:
        saved = self._requests.get(request_namespace(session_id, request_id))
        if saved is None:
            return None
        return deepcopy(saved[0]), saved[1]

    async def save_request(self, state: MainRuntimeState, expected_version: int | None) -> int:
        namespace = request_namespace(state.session_id, state.request_id)
        current = self._requests.get(namespace)
        current_version = current[1] if current is not None else 0
        if expected_version is not None and expected_version != current_version:
            raise ValueError("Agent runtime checkpoint version conflict")
        persisted = cast(MainRuntimeState, sanitize_persisted_value(state))
        version = current_version + 1
        self._requests[namespace] = (deepcopy(persisted), version)
        if persisted.active_interrupt is not None:
            self._active[persisted.session_id] = namespace
        elif self._active.get(persisted.session_id) == namespace:
            self._active.pop(persisted.session_id, None)
        return version

    async def load_active(self, session_id: str) -> tuple[str, MainRuntimeState, int] | None:
        namespace = self._active.get(session_id)
        if namespace is None:
            return None
        saved = self._requests.get(namespace)
        return (namespace, deepcopy(saved[0]), saved[1]) if saved is not None else None

    async def load_session(self, session_id: str) -> RuntimeSessionSnapshot | None:
        snapshot = self._sessions.get(session_id)
        return deepcopy(snapshot) if snapshot is not None else None

    async def save_session(self, snapshot: RuntimeSessionSnapshot) -> None:
        persisted = cast(RuntimeSessionSnapshot, sanitize_persisted_value(snapshot))
        self._sessions[snapshot.session_id] = deepcopy(persisted)


class LangGraphAgentRuntimeCheckpoint:
    """把 runtime namespace 映射到现有 LangGraph saver。"""

    _STATE_KEY = "__shijiajing_agent_runtime_state__"
    _SESSION_KEY = "__shijiajing_agent_runtime_session__"
    _ACTIVE_KEY = "__shijiajing_agent_runtime_active__"

    def __init__(self, saver: BaseCheckpointSaver[str]) -> None:
        self._saver = saver

    @staticmethod
    def _config(namespace: str) -> RunnableConfig:
        return cast(
            RunnableConfig,
            {
                "configurable": {
                    "thread_id": f"agent-runtime:{namespace}",
                    "checkpoint_ns": namespace,
                }
            },
        )

    async def _load(self, namespace: str, key: str) -> tuple[Any, int] | None:
        item = await self._saver.aget_tuple(self._config(namespace))
        if item is None:
            return None
        raw_values = item.checkpoint.get("channel_values")
        if not raw_values:
            return None
        values: dict[str, Any] = dict(raw_values)
        wrapped = values.get(key)
        if not isinstance(wrapped, dict) or "value" not in wrapped:
            return None
        wrapped_value = cast(dict[str, Any], wrapped)
        version: Any = wrapped_value.get("version", 0)
        return wrapped_value["value"], version if isinstance(version, int) else 0

    async def _save(self, namespace: str, key: str, value: Any, version: int) -> None:
        checkpoint = empty_checkpoint()
        checkpoint["channel_values"] = {key: {"value": value, "version": version}}
        await self._saver.aput(
            self._config(namespace),
            checkpoint,
            {"source": "update", "step": version, "parents": {}},
            {},
        )

    async def load_request(
        self, session_id: str, request_id: str
    ) -> tuple[MainRuntimeState, int] | None:
        loaded = await self._load(request_namespace(session_id, request_id), self._STATE_KEY)
        if loaded is None:
            return None
        value, version = loaded
        state = (
            value if isinstance(value, MainRuntimeState) else MainRuntimeState.model_validate(value)
        )
        return (
            state,
            version,
        )

    async def save_request(self, state: MainRuntimeState, expected_version: int | None) -> int:
        namespace = request_namespace(state.session_id, state.request_id)
        loaded = await self._load(namespace, self._STATE_KEY)
        current_version = loaded[1] if loaded is not None else 0
        if expected_version is not None and expected_version != current_version:
            raise ValueError("Agent runtime checkpoint version conflict")
        version = current_version + 1
        await self._save(namespace, self._STATE_KEY, state, version)
        if state.active_interrupt is not None:
            await self._save(
                f"agent-runtime-v1/{state.session_id}/__active__",
                self._ACTIVE_KEY,
                {"namespace": namespace},
                version,
            )
        else:
            # 清理旧的 active marker；保留一个显式空值比依赖 marker 的历史
            # checkpoint 被删除更容易兼容不同 LangGraph saver 实现。
            await self._save(
                f"agent-runtime-v1/{state.session_id}/__active__",
                self._ACTIVE_KEY,
                {"namespace": None},
                version,
            )
        return version

    async def load_active(self, session_id: str) -> tuple[str, MainRuntimeState, int] | None:
        loaded = await self._load(f"agent-runtime-v1/{session_id}/__active__", self._ACTIVE_KEY)
        if loaded is None or not isinstance(loaded[0], dict):
            return None
        active_value = cast(dict[str, Any], loaded[0])
        namespace = active_value.get("namespace")
        if not isinstance(namespace, str):
            return None
        state = await self._load(namespace, self._STATE_KEY)
        if state is None:
            return None
        value, version = state
        runtime_state = (
            value if isinstance(value, MainRuntimeState) else MainRuntimeState.model_validate(value)
        )
        return (
            namespace,
            runtime_state,
            version,
        )

    async def load_session(self, session_id: str) -> RuntimeSessionSnapshot | None:
        loaded = await self._load(session_namespace(session_id), self._SESSION_KEY)
        if loaded is None:
            return None
        value = loaded[0]
        return (
            value
            if isinstance(value, RuntimeSessionSnapshot)
            else RuntimeSessionSnapshot.model_validate(value)
        )

    async def save_session(self, snapshot: RuntimeSessionSnapshot) -> None:
        namespace = session_namespace(snapshot.session_id)
        loaded = await self._load(namespace, self._SESSION_KEY)
        version = (loaded[1] if loaded is not None else 0) + 1
        await self._save(namespace, self._SESSION_KEY, snapshot, version)


__all__ = [
    "AgentRuntimeCheckpointPort",
    "InMemoryAgentRuntimeCheckpoint",
    "LangGraphAgentRuntimeCheckpoint",
    "request_namespace",
    "session_namespace",
    "subagent_namespace",
]
