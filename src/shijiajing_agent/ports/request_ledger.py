"""请求结果账本端口。

账本与 LangGraph checkpoint 分离：checkpoint 保存 Supervisor/Agent 任务执行状态，账本保存每个
request_id
的 terminal response，避免同一 session 的旧请求因最新状态变化而重复执行。
"""

from __future__ import annotations

from typing import Protocol

from shijiajing_agent.contracts import AgentResponse
from shijiajing_agent.ports.lifecycle import ResourceLifecyclePort


class RequestLedgerPort(ResourceLifecyclePort, Protocol):
    async def get_response(self, session_id: str, request_id: str) -> AgentResponse | None: ...

    async def save_response(
        self,
        session_id: str,
        request_id: str,
        response: AgentResponse,
        expected_absent: bool = True,
    ) -> None: ...
