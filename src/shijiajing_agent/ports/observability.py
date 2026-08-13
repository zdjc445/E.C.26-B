"""可观测性 Port（方案 §4.1、§20）。

Trace sink 失败不能阻断业务结果，但必须增加本地错误计数；
Checkpoint 失败必须阻断成功提交。
"""

from __future__ import annotations

from typing import Protocol

from shijiajing_agent.contracts import AgentEvent


class TraceSinkPort(Protocol):
    """事件与节点记录 sink。失败不阻断业务。"""

    async def emit(self, event: AgentEvent) -> None: ...


class MetricsPort(Protocol):
    """指标输出。失败不阻断业务。"""

    def inc(self, name: str, labels: dict[str, str] | None = None, value: float = 1.0) -> None: ...

    def observe(self, name: str, value: float, labels: dict[str, str] | None = None) -> None: ...
