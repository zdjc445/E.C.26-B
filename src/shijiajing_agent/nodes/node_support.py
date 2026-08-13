"""节点公共支撑：计时、节点事件记录（方案 §20.1）。"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any

from shijiajing_agent.contracts import now_iso
from shijiajing_agent.state import AgentState, NodeEventRecord

NodeFn = Callable[[AgentState], Awaitable[dict[str, Any]]]


def set_dirty(state: AgentState, *flags: str) -> dict[str, dict[str, bool]]:
    """返回 dirty_flags 的增量字典（LangGraph 节点必须通过返回值传播状态）。"""
    current = dict(state.get("dirty_flags") or {})
    for f in flags:
        current[f] = True
    return {"dirty_flags": current}


def clear_dirty(state: AgentState, *flags: str) -> dict[str, dict[str, bool]]:
    current = dict(state.get("dirty_flags") or {})
    for f in flags:
        current[f] = False
    return {"dirty_flags": current}


def timed(node_name: str) -> Callable[[NodeFn], NodeFn]:
    """包装节点：计时并追加 NodeEventRecord，不影响业务结果。"""

    def decorator(fn: NodeFn) -> NodeFn:
        async def wrapper(state: AgentState) -> dict[str, Any]:
            started = time.monotonic()
            events: list[NodeEventRecord] = list(state.get("node_events") or [])
            try:
                delta = await fn(state)
                duration = (time.monotonic() - started) * 1000.0
                events.append(
                    NodeEventRecord(
                        trace_id=str(state.get("trace_id", "")),
                        session_id=str(state.get("session_id", "")),
                        request_id=str(state.get("request_id", "")),
                        turn_id=str(state.get("turn_id", "")),
                        node_name=node_name,
                        status="success",
                        started_at=now_iso(),
                        duration_ms=round(duration, 2),
                    )
                )
                delta["node_events"] = events
                return delta
            except Exception as exc:
                duration = (time.monotonic() - started) * 1000.0
                events.append(
                    NodeEventRecord(
                        trace_id=str(state.get("trace_id", "")),
                        session_id=str(state.get("session_id", "")),
                        request_id=str(state.get("request_id", "")),
                        turn_id=str(state.get("turn_id", "")),
                        node_name=node_name,
                        status="failed",
                        started_at=now_iso(),
                        duration_ms=round(duration, 2),
                        error_code=getattr(exc, "code", None) or "INTERNAL_ERROR",
                    )
                )
                delta = dict(node_events=events)
                delta["node_events"] = events
                raise

        return wrapper

    return decorator
