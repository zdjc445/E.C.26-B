"""追加式事件存储。诊断事件允许降级，内容冲突始终失败。"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
from typing import Any

from shijiajing_agent.contracts import AgentEventRecord, content_hash
from shijiajing_agent.errors import EventConflictError, EventStoreUnavailableError

_DDL = """
CREATE TABLE IF NOT EXISTS agent_event (
    event_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    request_id TEXT NOT NULL,
    turn_id TEXT NOT NULL,
    trace_id TEXT NOT NULL,
    agent_name TEXT NOT NULL,
    node_name TEXT,
    event_type TEXT NOT NULL,
    status TEXT,
    input_hash TEXT,
    output_hash TEXT,
    state_version INTEGER,
    payload_json TEXT NOT NULL,
    occurred_at TEXT NOT NULL
)
"""

_EVENT_TYPE_ORDER = {
    "turn_started": 0,
    "agent_started": 10,
    "agent_interrupted": 20,
    "agent_resumed": 30,
    "cache_hit": 40,
    "cache_miss": 40,
    "memory_recalled": 50,
    "agent_completed": 80,
    "agent_failed": 90,
    "memory_committed": 100,
    "memory_forgotten": 100,
    "request_result_committed": 110,
    "turn_completed": 120,
    "turn_failed": 130,
}


def event_sort_key(event: AgentEventRecord) -> tuple[str, int, str]:
    """返回所有 Event Store 共用的稳定时间线排序键。"""
    return (
        event.occurred_at,
        _EVENT_TYPE_ORDER.get(event.event_type, 60),
        event.event_id,
    )


def stable_event_id(
    session_id: str,
    request_id: str,
    turn_id: str,
    agent_name: str,
    node_name: str | None,
    event_type: str,
    attempt: int,
) -> str:
    return content_hash(
        {
            "session_id": session_id,
            "request_id": request_id,
            "turn_id": turn_id,
            "agent_name": agent_name,
            "node_name": node_name,
            "event_type": event_type,
            "attempt": attempt,
        }
    )


def memory_event_attempt(mutation_id: str) -> int:
    """把稳定 mutation_id 映射为 memory 一致性事件的稳定 attempt。"""
    try:
        return int(mutation_id, 16)
    except ValueError:
        # 兼容契约收紧前已写入的历史异常标识；新写入由 MemoryMutation pattern 拒绝。
        return int(content_hash(mutation_id), 16)


def same_event_content(left: AgentEventRecord, right: AgentEventRecord) -> bool:
    """比较 event_id 绑定的业务内容；发生时间是写入元数据，不参与冲突判断。"""
    return left.model_dump(mode="json", exclude={"occurred_at"}) == right.model_dump(
        mode="json", exclude={"occurred_at"}
    )


class InMemoryEventStore:
    def __init__(self) -> None:
        self._events: dict[str, AgentEventRecord] = {}
        self._lock = asyncio.Lock()

    async def setup(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def append(self, event: AgentEventRecord) -> None:
        async with self._lock:
            current = self._events.get(event.event_id)
            if current is not None:
                if same_event_content(current, event):
                    return
                raise EventConflictError("同一 event_id 内容不一致")
            self._events[event.event_id] = event.model_copy(deep=True)

    async def list_turn(self, session_id: str, turn_id: str) -> list[AgentEventRecord]:
        async with self._lock:
            return [
                event.model_copy(deep=True)
                for event in sorted(
                    [
                        event
                        for event in self._events.values()
                        if event.session_id == session_id and event.turn_id == turn_id
                    ],
                    key=event_sort_key,
                )
            ]


class SQLiteEventStoreAdapter:
    def __init__(self, dsn: str) -> None:
        path = dsn
        for prefix in ("sqlite:///", "sqlite://"):
            if path.startswith(prefix):
                path = path[len(prefix) :]
                break
        if not path:
            raise ValueError("SHIJIAJING_EVENT_STORE_DSN 不能为空")
        self._path = path
        self._conn: sqlite3.Connection | None = None
        self._lock = threading.RLock()
        self._closed = False

    def _connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self._path, check_same_thread=False)
            self._conn.execute("PRAGMA busy_timeout=5000")
        return self._conn

    async def setup(self) -> None:
        await asyncio.to_thread(self._setup_sync)

    def _setup_sync(self) -> None:
        with self._lock:
            if self._closed:
                raise EventStoreUnavailableError("Event Store 已关闭")
            self._connect().execute(_DDL)
            self._connect().commit()

    async def close(self) -> None:
        await asyncio.to_thread(self._close_sync)

    def _close_sync(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None
            self._closed = True

    async def append(self, event: AgentEventRecord) -> None:
        await asyncio.to_thread(self._append_sync, event)

    def _append_sync(self, event: AgentEventRecord) -> None:
        payload = json.dumps(event.payload, ensure_ascii=False, sort_keys=True)
        with self._lock:
            try:
                conn = self._connect()
                conn.execute(
                    "INSERT OR IGNORE INTO agent_event"
                    " (event_id, session_id, request_id, turn_id, trace_id, agent_name, node_name,"
                    " event_type, status, input_hash, output_hash, state_version, payload_json,"
                    " occurred_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        event.event_id,
                        event.session_id,
                        event.request_id,
                        event.turn_id,
                        event.trace_id,
                        event.agent_name,
                        event.node_name,
                        event.event_type,
                        event.status,
                        event.input_hash,
                        event.output_hash,
                        event.state_version,
                        payload,
                        event.occurred_at,
                    ),
                )
                conn.commit()
                row = conn.execute(
                    "SELECT session_id, request_id, turn_id, trace_id, agent_name, node_name,"
                    " event_type, status, input_hash, output_hash, state_version, payload_json,"
                    " occurred_at FROM agent_event WHERE event_id = ?",
                    (event.event_id,),
                ).fetchone()
                if row is None:
                    raise EventStoreUnavailableError("Event Store 写入后无法读取 event_id")
                current = _row_to_event(event.event_id, row)
                if same_event_content(current, event):
                    return
                raise EventConflictError("同一 event_id 内容不一致")
            except EventConflictError:
                raise
            except Exception as exc:
                raise EventStoreUnavailableError(f"Event Store 写入失败: {exc}") from exc

    async def list_turn(self, session_id: str, turn_id: str) -> list[AgentEventRecord]:
        return await asyncio.to_thread(self._list_sync, session_id, turn_id)

    def _list_sync(self, session_id: str, turn_id: str) -> list[AgentEventRecord]:
        with self._lock:
            try:
                rows = (
                    self._connect()
                    .execute(
                        "SELECT event_id, session_id, request_id, turn_id, trace_id, agent_name,"
                        " node_name, event_type, status, input_hash, output_hash, state_version,"
                        " payload_json, occurred_at FROM agent_event"
                        " WHERE session_id = ? AND turn_id = ? ORDER BY occurred_at, event_id",
                        (session_id, turn_id),
                    )
                    .fetchall()
                )
                return sorted([_row_to_event(row[0], row[1:]) for row in rows], key=event_sort_key)
            except Exception as exc:
                raise EventStoreUnavailableError(f"Event Store 读取失败: {exc}") from exc


def _row_to_event(event_id: str, row: tuple[Any, ...]) -> AgentEventRecord:
    return AgentEventRecord(
        event_id=event_id,
        session_id=row[0],
        request_id=row[1],
        turn_id=row[2],
        trace_id=row[3],
        agent_name=row[4],
        node_name=row[5],
        event_type=row[6],
        status=row[7],
        input_hash=row[8],
        output_hash=row[9],
        state_version=row[10],
        payload=json.loads(row[11]),
        occurred_at=row[12],
    )


def make_event_store_adapter(
    backend: str,
    dsn: str | None,
    *,
    pool_min_size: int = 1,
    pool_max_size: int = 4,
    pool_timeout_seconds: float = 30.0,
) -> Any:
    normalized = backend.lower()
    if normalized == "disabled":
        return None
    if normalized == "sqlite":
        return SQLiteEventStoreAdapter(dsn or "")
    if normalized == "postgres":
        return PostgresEventStoreAdapter(
            dsn or "",
            min_size=pool_min_size,
            max_size=pool_max_size,
            timeout_seconds=pool_timeout_seconds,
        )
    raise ValueError(f"未知 event_store_backend: {backend}")


class PostgresEventStoreAdapter:
    """PostgreSQL 追加式事件实现，使用 event_id 做幂等键。"""

    def __init__(
        self,
        dsn: str,
        *,
        max_size: int = 4,
        min_size: int = 1,
        timeout_seconds: float = 30.0,
    ) -> None:
        if not dsn:
            raise ValueError("SHIJIAJING_EVENT_STORE_DSN 不能为空")
        from psycopg_pool import AsyncConnectionPool

        self._pool: Any = AsyncConnectionPool(
            dsn,
            min_size=min_size,
            max_size=max_size,
            timeout=timeout_seconds,
            open=False,
        )

    async def setup(self) -> None:
        try:
            await self._pool.open()
            async with self._pool.connection() as conn:
                async with conn.transaction():
                    await conn.execute(_DDL)
        except Exception as exc:
            raise EventStoreUnavailableError(f"Event Store setup 失败: {exc}") from exc

    async def close(self) -> None:
        await self._pool.close()

    async def append(self, event: AgentEventRecord) -> None:
        payload = json.dumps(event.payload, ensure_ascii=False, sort_keys=True)
        try:
            async with self._pool.connection() as conn:
                async with conn.transaction():
                    await conn.execute(
                        "INSERT INTO agent_event"
                        " (event_id, session_id, request_id, turn_id, trace_id, agent_name,"
                        " node_name, event_type, status, input_hash, output_hash, state_version,"
                        " payload_json, occurred_at)"
                        " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
                        " ON CONFLICT (event_id) DO NOTHING",
                        (
                            event.event_id,
                            event.session_id,
                            event.request_id,
                            event.turn_id,
                            event.trace_id,
                            event.agent_name,
                            event.node_name,
                            event.event_type,
                            event.status,
                            event.input_hash,
                            event.output_hash,
                            event.state_version,
                            payload,
                            event.occurred_at,
                        ),
                    )
                    cur = await conn.execute(
                        "SELECT session_id, request_id, turn_id, trace_id, agent_name, node_name,"
                        " event_type, status, input_hash, output_hash, state_version, payload_json,"
                        " occurred_at FROM agent_event WHERE event_id = %s",
                        (event.event_id,),
                    )
                    row = await cur.fetchone()
                    if row is None:
                        raise EventStoreUnavailableError("Event Store 写入后无法读取 event_id")
                    current = _row_to_event(event.event_id, row)
                    if same_event_content(current, event):
                        return
                    raise EventConflictError("同一 event_id 内容不一致")
        except EventConflictError:
            raise
        except Exception as exc:
            raise EventStoreUnavailableError(f"Event Store 写入失败: {exc}") from exc

    async def list_turn(self, session_id: str, turn_id: str) -> list[AgentEventRecord]:
        try:
            async with self._pool.connection() as conn:
                cur = await conn.execute(
                    "SELECT event_id, session_id, request_id, turn_id, trace_id, agent_name,"
                    " node_name, event_type, status, input_hash, output_hash, state_version,"
                    " payload_json, occurred_at FROM agent_event"
                    " WHERE session_id = %s AND turn_id = %s ORDER BY occurred_at, event_id",
                    (session_id, turn_id),
                )
                rows = await cur.fetchall()
            return sorted([_row_to_event(row[0], row[1:]) for row in rows], key=event_sort_key)
        except Exception as exc:
            raise EventStoreUnavailableError(f"Event Store 读取失败: {exc}") from exc
