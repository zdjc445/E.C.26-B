"""节点公共支撑：计时、节点事件记录（方案 §20.1）。"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any

from shijiajing_agent.adapters.ark_models import take_model_calls
from shijiajing_agent.adapters.event_store import stable_event_id
from shijiajing_agent.contracts import AgentEvent, AgentEventRecord, EventType, NodeStatus, now_iso
from shijiajing_agent.ports.dependencies import AgentDependenciesPort
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


async def record_cache_event(
    deps: AgentDependenciesPort,
    state: AgentState,
    *,
    node_name: str,
    namespace: str,
    cache_key: str,
    hit: bool,
) -> None:
    """记录 cache hit/miss；只写哈希 key 与命名空间，不写业务输入。"""
    event_store = getattr(deps, "event_store", None)
    request = state["current_request"]
    event_type = "cache_hit" if hit else "cache_miss"
    attempt = sum(
        1 for event in state.get("node_events") or [] if event.get("node_name") == node_name
    )
    if event_store is not None:
        try:
            await event_store.append(
                AgentEventRecord(
                    event_id=stable_event_id(
                        request.session_id,
                        request.request_id,
                        str(state.get("turn_id") or ""),
                        "supervisor",
                        node_name,
                        event_type,
                        attempt,
                    ),
                    session_id=request.session_id,
                    request_id=request.request_id,
                    turn_id=str(state.get("turn_id") or ""),
                    trace_id=str(state.get("trace_id") or ""),
                    agent_name="supervisor",
                    node_name=node_name,
                    event_type=event_type,
                    payload={"namespace": namespace, "cache_key": cache_key},
                    occurred_at=now_iso(),
                )
            )
        except Exception:
            try:
                deps.metrics.inc("event_store_failure_total")
            except Exception:
                pass
    trace_sink = getattr(deps, "trace", None)
    trace_backend = getattr(getattr(deps, "settings", None), "trace_backend", None)
    if trace_sink is not None and (trace_backend is None or trace_backend == "opentelemetry"):
        try:
            await trace_sink.emit(
                AgentEvent(
                    session_id=request.session_id,
                    request_id=request.request_id,
                    turn_id=str(state.get("turn_id") or ""),
                    trace_id=str(state.get("trace_id") or ""),
                    event_type=EventType.NODE_COMPLETED,
                    timestamp=now_iso(),
                    agent_name="supervisor",
                    node_name="cache",
                    status=NodeStatus.SUCCESS,
                    cache_hit=hit,
                )
            )
        except Exception:
            try:
                deps.metrics.inc("trace_sink_failure_total")
            except Exception:
                pass


def timed(node_name: str) -> Callable[[NodeFn], NodeFn]:
    """包装节点：计时并追加 NodeEventRecord，不影响业务结果。"""

    def decorator(fn: NodeFn) -> NodeFn:
        async def wrapper(state: AgentState) -> dict[str, Any]:
            started = time.monotonic()
            events: list[NodeEventRecord] = list(state.get("node_events") or [])
            attempt = sum(1 for event in events if event.get("node_name") == node_name)
            try:
                delta = await fn(state)
                duration = (time.monotonic() - started) * 1000.0
                model_call = _last_model_call()
                events.append(
                    _node_event(
                        state,
                        node_name=node_name,
                        retry_count=attempt,
                        status="success",
                        duration_ms=round(duration, 2),
                        model_call=model_call,
                    )
                )
                delta["node_events"] = events
                return delta
            except Exception as exc:
                try:
                    attribute_name = "node_name"
                    setattr(exc, attribute_name, node_name)
                except Exception:
                    pass
                duration = (time.monotonic() - started) * 1000.0
                model_call = _last_model_call()
                events.append(
                    _node_event(
                        state,
                        node_name=node_name,
                        retry_count=attempt,
                        status="failed",
                        started_at=now_iso(),
                        duration_ms=round(duration, 2),
                        error_code=getattr(exc, "code", None) or "INTERNAL_ERROR",
                        model_call=model_call,
                    )
                )
                delta = dict(node_events=events)
                delta["node_events"] = events
                raise

        return wrapper

    return decorator


def _last_model_call() -> Any | None:
    calls = take_model_calls()
    return calls[-1] if calls else None


def _node_event(
    state: AgentState,
    *,
    node_name: str,
    retry_count: int,
    status: str,
    started_at: str | None = None,
    duration_ms: float,
    error_code: str | None = None,
    model_call: Any | None = None,
) -> NodeEventRecord:
    event = NodeEventRecord(
        trace_id=str(state.get("trace_id", "")),
        session_id=str(state.get("session_id", "")),
        request_id=str(state.get("request_id", "")),
        turn_id=str(state.get("turn_id", "")),
        node_name=node_name,
        retry_count=retry_count,
        status=status,
        started_at=started_at or now_iso(),
        duration_ms=duration_ms,
        error_code=error_code,
    )
    if model_call is not None:
        event.update(
            {
                "model": model_call.model,
                "prompt_version": model_call.prompt_version,
                "input_hash": model_call.input_hash,
                "output_hash": model_call.output_hash,
                "token_usage": model_call.token_usage,
            }
        )
    return event
