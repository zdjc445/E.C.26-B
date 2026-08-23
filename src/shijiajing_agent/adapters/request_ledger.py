"""Request Ledger 的 SQLite/PostgreSQL/内存实现。"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
from typing import Any

from shijiajing_agent.contracts import AgentResponse, content_hash, now_iso
from shijiajing_agent.errors import RequestLedgerUnavailableError, SessionConflictError

_SQLITE_DDL = """
CREATE TABLE IF NOT EXISTS agent_request_result (
    session_id  TEXT NOT NULL,
    request_id  TEXT NOT NULL,
    response_json TEXT NOT NULL,
    response_hash TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    PRIMARY KEY (session_id, request_id)
)
"""


def _response_json(response: AgentResponse) -> tuple[str, str]:
    payload = response.model_dump(mode="json")
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return raw, content_hash(payload)


class InMemoryRequestLedger:
    """测试和单进程开发实现；行为与数据库适配器一致。"""

    def __init__(self) -> None:
        self._responses: dict[tuple[str, str], AgentResponse] = {}
        self._lock = asyncio.Lock()

    async def setup(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def get_response(self, session_id: str, request_id: str) -> AgentResponse | None:
        async with self._lock:
            response = self._responses.get((session_id, request_id))
            return response.model_copy(deep=True) if response is not None else None

    async def save_response(
        self,
        session_id: str,
        request_id: str,
        response: AgentResponse,
        expected_absent: bool = True,
    ) -> None:
        del expected_absent
        async with self._lock:
            key = (session_id, request_id)
            current = self._responses.get(key)
            if current is not None:
                if _response_json(current)[1] == _response_json(response)[1]:
                    return
                raise SessionConflictError("同一 request_id 已存在不同响应")
            self._responses[key] = response.model_copy(deep=True)


class SQLiteRequestLedgerAdapter:
    def __init__(self, dsn: str) -> None:
        path = dsn
        for prefix in ("sqlite:///", "sqlite://"):
            if path.startswith(prefix):
                path = path[len(prefix) :]
                break
        if not path:
            raise ValueError("SHIJIAJING_REQUEST_LEDGER_DSN 不能为空")
        self._path = path
        self._conn: sqlite3.Connection | None = None
        self._lock = threading.RLock()
        self._closed = False

    async def setup(self) -> None:
        await asyncio.to_thread(self._setup_sync)

    def _setup_sync(self) -> None:
        with self._lock:
            if self._closed:
                raise RequestLedgerUnavailableError("Request Ledger 已关闭")
            conn = self._connect()
            conn.execute(_SQLITE_DDL)
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self._path, check_same_thread=False)
            self._conn.execute("PRAGMA busy_timeout=5000")
        return self._conn

    async def close(self) -> None:
        await asyncio.to_thread(self._close_sync)

    def _close_sync(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None
            self._closed = True

    async def get_response(self, session_id: str, request_id: str) -> AgentResponse | None:
        return await asyncio.to_thread(self._get_sync, session_id, request_id)

    def _get_sync(self, session_id: str, request_id: str) -> AgentResponse | None:
        with self._lock:
            try:
                row = (
                    self._connect()
                    .execute(
                        "SELECT response_json, response_hash FROM agent_request_result"
                        " WHERE session_id = ? AND request_id = ?",
                        (session_id, request_id),
                    )
                    .fetchone()
                )
                if row is None:
                    return None
                response = AgentResponse.model_validate(json.loads(row[0]))
                if _response_json(response)[1] != row[1]:
                    raise RequestLedgerUnavailableError("Request Ledger 响应摘要不一致")
                return response
            except Exception as exc:
                if isinstance(exc, RequestLedgerUnavailableError):
                    raise
                raise RequestLedgerUnavailableError(f"Request Ledger 读取失败: {exc}") from exc

    async def save_response(
        self,
        session_id: str,
        request_id: str,
        response: AgentResponse,
        expected_absent: bool = True,
    ) -> None:
        await asyncio.to_thread(self._save_sync, session_id, request_id, response, expected_absent)

    def _save_sync(
        self,
        session_id: str,
        request_id: str,
        response: AgentResponse,
        expected_absent: bool,
    ) -> None:
        raw, response_hash = _response_json(response)
        with self._lock:
            if self._closed:
                raise RequestLedgerUnavailableError("Request Ledger 已关闭")
            conn = self._connect()
            try:
                conn.execute("BEGIN IMMEDIATE")
                row = conn.execute(
                    "SELECT response_json, response_hash FROM agent_request_result"
                    " WHERE session_id = ? AND request_id = ?",
                    (session_id, request_id),
                ).fetchone()
                if row is not None:
                    conn.rollback()
                    if row[1] == response_hash:
                        return
                    raise SessionConflictError("同一 request_id 已存在不同响应")
                conn.execute(
                    "INSERT INTO agent_request_result"
                    " (session_id, request_id, response_json, response_hash, created_at)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (session_id, request_id, raw, response_hash, now_iso()),
                )
                conn.commit()
            except SessionConflictError:
                raise
            except sqlite3.Error as exc:
                conn.rollback()
                if not expected_absent:
                    raise RequestLedgerUnavailableError(f"Request Ledger 写入失败: {exc}") from exc
                raise RequestLedgerUnavailableError(f"Request Ledger 写入失败: {exc}") from exc


class PostgresRequestLedgerAdapter:
    """生产 PostgreSQL 实现；psycopg_pool 只在实例化时导入。"""

    def __init__(
        self,
        dsn: str,
        *,
        max_size: int = 4,
        min_size: int = 1,
        timeout_seconds: float = 30.0,
    ) -> None:
        if not dsn:
            raise ValueError("SHIJIAJING_REQUEST_LEDGER_DSN 不能为空")
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
                await conn.execute(
                    _SQLITE_DDL.replace("?", "%s")
                    .replace("TEXT NOT NULL", "TEXT NOT NULL")
                    .replace(
                        "PRIMARY KEY (session_id, request_id)",
                        "PRIMARY KEY (session_id, request_id)",
                    )
                )
        except Exception as exc:
            raise RequestLedgerUnavailableError(f"Request Ledger setup 失败: {exc}") from exc

    async def close(self) -> None:
        await self._pool.close()

    async def get_response(self, session_id: str, request_id: str) -> AgentResponse | None:
        try:
            async with self._pool.connection() as conn:
                cur = await conn.execute(
                    "SELECT response_json, response_hash FROM agent_request_result"
                    " WHERE session_id = %s AND request_id = %s",
                    (session_id, request_id),
                )
                row = await cur.fetchone()
            if row is None:
                return None
            response = AgentResponse.model_validate(json.loads(row[0]))
            if _response_json(response)[1] != row[1]:
                raise RequestLedgerUnavailableError("Request Ledger 响应摘要不一致")
            return response
        except RequestLedgerUnavailableError:
            raise
        except Exception as exc:
            raise RequestLedgerUnavailableError(f"Request Ledger 读取失败: {exc}") from exc

    async def save_response(
        self,
        session_id: str,
        request_id: str,
        response: AgentResponse,
        expected_absent: bool = True,
    ) -> None:
        del expected_absent
        raw, response_hash = _response_json(response)
        try:
            async with self._pool.connection() as conn:
                async with conn.transaction():
                    await conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (session_id,))
                    cur = await conn.execute(
                        "SELECT response_hash FROM agent_request_result"
                        " WHERE session_id = %s AND request_id = %s",
                        (session_id, request_id),
                    )
                    row = await cur.fetchone()
                    if row is not None:
                        if row[0] == response_hash:
                            return
                        raise SessionConflictError("同一 request_id 已存在不同响应")
                    await conn.execute(
                        "INSERT INTO agent_request_result"
                        " (session_id, request_id, response_json, response_hash, created_at)"
                        " VALUES (%s, %s, %s, %s, %s)",
                        (session_id, request_id, raw, response_hash, now_iso()),
                    )
        except SessionConflictError:
            raise
        except Exception as exc:
            raise RequestLedgerUnavailableError(f"Request Ledger 写入失败: {exc}") from exc


def make_request_ledger(
    backend: str,
    dsn: str | None,
    *,
    pool_min_size: int = 1,
    pool_max_size: int = 4,
    pool_timeout_seconds: float = 30.0,
) -> Any:
    normalized = backend.lower()
    if normalized == "sqlite":
        return SQLiteRequestLedgerAdapter(dsn or "")
    if normalized == "postgres":
        return PostgresRequestLedgerAdapter(
            dsn or "",
            min_size=pool_min_size,
            max_size=pool_max_size,
            timeout_seconds=pool_timeout_seconds,
        )
    if normalized == "disabled":
        return InMemoryRequestLedger()
    raise ValueError(f"未知 request_ledger_backend: {backend}")
