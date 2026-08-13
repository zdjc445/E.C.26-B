"""Checkpoint Port（方案 §4.1、§17）。

``session_id`` 作为 LangGraph ``thread_id``；每个节点完成后保存 super-step 状态。
Checkpoint 保存 ``schema_version`` 和 ``state_version``，不兼容版本不得直接加载。

Checkpoint 失败必须阻断成功提交（trace sink 失败不阻断，见 ``observability``）。
"""

from __future__ import annotations

from typing import Protocol

from shijiajing_agent.state import AgentState


class CheckpointPort(Protocol):
    """会话 Checkpoint：按 session_id 保存/加载 super-step 状态。"""

    async def load(self, session_id: str) -> tuple[AgentState, int] | None:
        """返回 (state, version)；无历史返回 None。"""
        ...

    async def save(self, session_id: str, state: AgentState, expected_version: int | None) -> int:
        """乐观版本检查保存。版本冲突时抛 SessionConflictError。返回新版本号。"""
        ...
