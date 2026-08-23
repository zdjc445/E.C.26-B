"""显式长期记忆的 SQLite、禁用和 PostgreSQL 装配入口。"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
from typing import Any

from shijiajing_agent.contracts import (
    MemoryMutation,
    MemoryOperation,
    MemoryQuery,
    MemoryRecord,
    MemoryStatus,
    content_hash,
    now_iso,
)
from shijiajing_agent.domain.memory_policy import memory_id, validate_mutation
from shijiajing_agent.errors import MemoryConflictError, MemoryUnavailableError

_DDL = """
CREATE TABLE IF NOT EXISTS user_memory (
    memory_id TEXT PRIMARY KEY,
    memory_owner_id TEXT NOT NULL,
    memory_key TEXT NOT NULL,
    scope_key TEXT NOT NULL,
    value_json TEXT NOT NULL,
    apply_mode TEXT NOT NULL,
    confidence REAL NOT NULL,
    status TEXT NOT NULL,
    source_session_id TEXT NOT NULL,
    source_request_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    expires_at TEXT,
    UNIQUE(memory_owner_id, scope_key, memory_key)
);
CREATE TABLE IF NOT EXISTS memory_mutation (
    mutation_id TEXT PRIMARY KEY,
    memory_owner_id TEXT NOT NULL,
    operation TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    applied_at TEXT NOT NULL
);
"""


def _mutation_matches(payload_json: str, mutation: MemoryMutation) -> bool:
    """比较 mutation_id 绑定的完整内容，而不是只比较 owner。"""
    try:
        stored_payload = json.loads(payload_json)
    except (TypeError, ValueError) as exc:
        raise MemoryUnavailableError("memory_mutation payload 已损坏") from exc
    return content_hash(stored_payload) == content_hash(mutation.model_dump(mode="json"))


class DisabledMemoryAdapter:
    async def setup(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def recall(self, memory_owner_id: str, query: MemoryQuery) -> list[MemoryRecord]:
        del memory_owner_id, query
        return []

    async def commit(
        self, memory_owner_id: str, mutations: list[MemoryMutation]
    ) -> list[MemoryRecord]:
        del memory_owner_id, mutations
        return []

    async def list_memories(self, memory_owner_id: str) -> list[MemoryRecord]:
        del memory_owner_id
        return []

    async def clear_owner(self, memory_owner_id: str, mutation_id: str) -> None:
        del memory_owner_id, mutation_id


class SQLiteMemoryAdapter:
    def __init__(self, dsn: str) -> None:
        path = dsn
        for prefix in ("sqlite:///", "sqlite://"):
            if path.startswith(prefix):
                path = path[len(prefix) :]
                break
        if not path:
            raise ValueError("SHIJIAJING_MEMORY_DSN 不能为空")
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
                raise MemoryUnavailableError("Memory adapter 已关闭")
            conn = self._connect()
            conn.executescript(_DDL)
            conn.commit()

    async def close(self) -> None:
        await asyncio.to_thread(self._close_sync)

    def _close_sync(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None
            self._closed = True

    async def recall(self, memory_owner_id: str, query: MemoryQuery) -> list[MemoryRecord]:
        return await asyncio.to_thread(self._recall_sync, memory_owner_id, query)

    def _recall_sync(self, owner: str, query: MemoryQuery) -> list[MemoryRecord]:
        with self._lock:
            try:
                placeholders = ",".join("?" for _ in query.scope_keys)
                params: list[Any] = [owner, *query.scope_keys]
                sql = (
                    "SELECT * FROM user_memory WHERE memory_owner_id = ? AND scope_key IN ("
                    + placeholders
                    + ") AND status = 'active' AND (expires_at IS NULL OR expires_at > ?)"
                )
                params.append(now_iso())
                if query.memory_keys:
                    key_ph = ",".join("?" for _ in query.memory_keys)
                    sql += f" AND memory_key IN ({key_ph})"
                    params.extend(query.memory_keys)
                sql += " ORDER BY updated_at DESC LIMIT ?"
                params.append(query.limit)
                rows = self._connect().execute(sql, params).fetchall()
                return [_row_to_record(row) for row in rows]
            except Exception as exc:
                raise MemoryUnavailableError(f"Memory recall 失败: {exc}") from exc

    async def list_memories(self, memory_owner_id: str) -> list[MemoryRecord]:
        return await asyncio.to_thread(self._list_sync, memory_owner_id)

    def _list_sync(self, owner: str) -> list[MemoryRecord]:
        with self._lock:
            try:
                rows = (
                    self._connect()
                    .execute(
                        "SELECT * FROM user_memory WHERE memory_owner_id = ?"
                        " ORDER BY updated_at DESC",
                        (owner,),
                    )
                    .fetchall()
                )
                return [_row_to_record(row) for row in rows]
            except Exception as exc:
                raise MemoryUnavailableError(f"Memory list 失败: {exc}") from exc

    async def commit(
        self, memory_owner_id: str, mutations: list[MemoryMutation]
    ) -> list[MemoryRecord]:
        return await asyncio.to_thread(self._commit_sync, memory_owner_id, mutations)

    def _commit_sync(self, owner: str, mutations: list[MemoryMutation]) -> list[MemoryRecord]:
        validated_mutations = [validate_mutation(mutation) for mutation in mutations]
        with self._lock:
            conn = self._connect()
            try:
                conn.execute("BEGIN IMMEDIATE")
                changed: list[MemoryRecord] = []
                for mutation in validated_mutations:
                    exists = conn.execute(
                        "SELECT memory_owner_id, payload_json FROM memory_mutation"
                        " WHERE mutation_id = ?",
                        (mutation.mutation_id,),
                    ).fetchone()
                    if exists is not None:
                        if exists[0] != owner:
                            raise MemoryConflictError("mutation_id 不能跨 memory owner 重用")
                        if not _mutation_matches(exists[1], mutation):
                            raise MemoryConflictError("同一 mutation_id 内容不一致")
                        continue
                    if mutation.operation is MemoryOperation.CLEAR_OWNER:
                        self._clear_sync_in_transaction(conn, owner)
                        conn.execute(
                            "INSERT INTO memory_mutation"
                            " (mutation_id, memory_owner_id, operation, payload_json, applied_at)"
                            " VALUES (?, ?, ?, ?, ?)",
                            (
                                mutation.mutation_id,
                                owner,
                                mutation.operation.value,
                                json.dumps(mutation.model_dump(mode="json"), ensure_ascii=False),
                                now_iso(),
                            ),
                        )
                        continue
                    if mutation.memory_key is None:
                        raise MemoryConflictError("记忆变更缺少 memory_key")
                    if mutation.source_session_id == "" or mutation.source_request_id == "":
                        raise MemoryConflictError("记忆变更缺少来源标识")
                    current = conn.execute(
                        "SELECT * FROM user_memory WHERE memory_owner_id = ?"
                        " AND scope_key = ? AND memory_key = ?",
                        (owner, mutation.scope_key, mutation.memory_key),
                    ).fetchone()
                    if mutation.operation is MemoryOperation.FORGET and current is None:
                        conn.execute(
                            "INSERT INTO memory_mutation"
                            " (mutation_id, memory_owner_id, operation, payload_json, applied_at)"
                            " VALUES (?, ?, ?, ?, ?)",
                            (
                                mutation.mutation_id,
                                owner,
                                mutation.operation.value,
                                json.dumps(mutation.model_dump(mode="json"), ensure_ascii=False),
                                now_iso(),
                            ),
                        )
                        continue
                    record = _apply_mutation(conn, owner, mutation, current)
                    changed.append(record)
                    conn.execute(
                        "INSERT INTO memory_mutation"
                        " (mutation_id, memory_owner_id, operation, payload_json, applied_at)"
                        " VALUES (?, ?, ?, ?, ?)",
                        (
                            mutation.mutation_id,
                            owner,
                            mutation.operation.value,
                            json.dumps(mutation.model_dump(mode="json"), ensure_ascii=False),
                            now_iso(),
                        ),
                    )
                conn.commit()
                return changed
            except (MemoryConflictError, sqlite3.Error) as exc:
                conn.rollback()
                if isinstance(exc, MemoryConflictError):
                    raise
                raise MemoryUnavailableError(f"Memory commit 失败: {exc}") from exc

    def _clear_sync_in_transaction(self, conn: sqlite3.Connection, owner: str) -> None:
        now = now_iso()
        conn.execute(
            "UPDATE user_memory SET status = 'forgotten', version = version + 1, updated_at = ?"
            " WHERE memory_owner_id = ? AND status = 'active'",
            (now, owner),
        )

    async def clear_owner(self, memory_owner_id: str, mutation_id: str) -> None:
        mutation = MemoryMutation(
            mutation_id=mutation_id,
            operation=MemoryOperation.CLEAR_OWNER,
            source_session_id="memory-admin",
            source_request_id=mutation_id,
        )
        await self.commit(memory_owner_id, [mutation])


def _apply_mutation(
    conn: sqlite3.Connection,
    owner: str,
    mutation: MemoryMutation,
    current: tuple[Any, ...] | None,
) -> MemoryRecord:
    now = now_iso()
    if mutation.operation is MemoryOperation.FORGET:
        if current is None:
            raise MemoryConflictError("不能遗忘不存在的记忆")
        record = _row_to_record(current).model_copy(
            update={
                "status": MemoryStatus.FORGOTTEN,
                "version": _row_to_record(current).version + 1,
                "updated_at": now,
            }
        )
        conn.execute(
            "UPDATE user_memory SET status = 'forgotten', version = ?, updated_at = ?"
            " WHERE memory_id = ?",
            (record.version, now, record.memory_id),
        )
        return record

    assert mutation.value is not None
    assert mutation.apply_mode is not None
    stable_id = memory_id(owner, mutation.scope_key, mutation.memory_key or "")
    version = (_row_to_record(current).version + 1) if current is not None else 1
    created = _row_to_record(current).created_at if current is not None else now
    record = MemoryRecord(
        memory_id=stable_id,
        memory_owner_id=owner,
        memory_key=mutation.memory_key or "",
        scope_key=mutation.scope_key,
        value=mutation.value,
        apply_mode=mutation.apply_mode,
        confidence=1.0,
        status=MemoryStatus.ACTIVE,
        source_session_id=mutation.source_session_id,
        source_request_id=mutation.source_request_id,
        version=version,
        created_at=created,
        updated_at=now,
    )
    conn.execute(
        "INSERT INTO user_memory"
        " (memory_id, memory_owner_id, memory_key, scope_key, value_json, apply_mode, confidence,"
        " status, source_session_id, source_request_id, version, created_at, updated_at,"
        " expires_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        " ON CONFLICT(memory_owner_id, scope_key, memory_key) DO UPDATE SET"
        " value_json=excluded.value_json, apply_mode=excluded.apply_mode,"
        " confidence=excluded.confidence,"
        " status=excluded.status, source_session_id=excluded.source_session_id,"
        " source_request_id=excluded.source_request_id, version=excluded.version,"
        " updated_at=excluded.updated_at, expires_at=excluded.expires_at",
        (
            record.memory_id,
            record.memory_owner_id,
            record.memory_key,
            record.scope_key,
            json.dumps(record.value, ensure_ascii=False),
            record.apply_mode.value,
            record.confidence,
            record.status.value,
            record.source_session_id,
            record.source_request_id,
            record.version,
            record.created_at,
            record.updated_at,
            record.expires_at,
        ),
    )
    return record


def _row_to_record(row: tuple[Any, ...]) -> MemoryRecord:
    (
        memory_id_value,
        owner,
        key,
        scope,
        value_json,
        apply_mode,
        confidence,
        status,
        source_session,
        source_request,
        version,
        created_at,
        updated_at,
        expires_at,
    ) = row
    return MemoryRecord(
        memory_id=memory_id_value,
        memory_owner_id=owner,
        memory_key=key,
        scope_key=scope,
        value=json.loads(value_json),
        apply_mode=apply_mode,
        confidence=confidence,
        status=status,
        source_session_id=source_session,
        source_request_id=source_request,
        version=version,
        created_at=created_at,
        updated_at=updated_at,
        expires_at=expires_at,
    )


def make_memory_adapter(
    backend: str,
    dsn: str | None,
    *,
    pool_min_size: int = 1,
    pool_max_size: int = 4,
    pool_timeout_seconds: float = 30.0,
) -> Any:
    normalized = backend.lower()
    if normalized == "disabled":
        return DisabledMemoryAdapter()
    if normalized == "sqlite":
        return SQLiteMemoryAdapter(dsn or "")
    if normalized == "postgres":
        return PostgresMemoryAdapter(
            dsn or "",
            min_size=pool_min_size,
            max_size=pool_max_size,
            timeout_seconds=pool_timeout_seconds,
        )
    raise ValueError(f"未知 memory_backend: {backend}")


class PostgresMemoryAdapter:
    """PostgreSQL 长期记忆实现；连接池只在 PostgreSQL backend 启用时导入。"""

    def __init__(
        self,
        dsn: str,
        *,
        max_size: int = 4,
        min_size: int = 1,
        timeout_seconds: float = 30.0,
    ) -> None:
        if not dsn:
            raise ValueError("SHIJIAJING_MEMORY_DSN 不能为空")
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
                    for statement in _DDL.split(";"):
                        if statement.strip():
                            await conn.execute(statement)
        except Exception as exc:
            raise MemoryUnavailableError(f"Memory setup 失败: {exc}") from exc

    async def close(self) -> None:
        await self._pool.close()

    async def recall(self, memory_owner_id: str, query: MemoryQuery) -> list[MemoryRecord]:
        try:
            placeholders = ",".join("%s" for _ in query.scope_keys)
            params: list[Any] = [memory_owner_id, *query.scope_keys, now_iso()]
            sql = (
                "SELECT memory_id, memory_owner_id, memory_key, scope_key, value_json,"
                " apply_mode, confidence, status, source_session_id, source_request_id,"
                " version, created_at, updated_at, expires_at FROM user_memory"
                f" WHERE memory_owner_id = %s AND scope_key IN ({placeholders})"
                " AND status = 'active' AND (expires_at IS NULL OR expires_at > %s)"
            )
            if query.memory_keys:
                key_placeholders = ",".join("%s" for _ in query.memory_keys)
                sql += f" AND memory_key IN ({key_placeholders})"
                params.extend(query.memory_keys)
            sql += " ORDER BY updated_at DESC LIMIT %s"
            params.append(query.limit)
            async with self._pool.connection() as conn:
                cur = await conn.execute(sql, params)
                rows = await cur.fetchall()
            return [_row_to_record(row) for row in rows]
        except Exception as exc:
            raise MemoryUnavailableError(f"Memory recall 失败: {exc}") from exc

    async def list_memories(self, memory_owner_id: str) -> list[MemoryRecord]:
        try:
            async with self._pool.connection() as conn:
                cur = await conn.execute(
                    "SELECT memory_id, memory_owner_id, memory_key, scope_key, value_json,"
                    " apply_mode, confidence, status, source_session_id, source_request_id,"
                    " version, created_at, updated_at, expires_at FROM user_memory"
                    " WHERE memory_owner_id = %s ORDER BY updated_at DESC",
                    (memory_owner_id,),
                )
                rows = await cur.fetchall()
            return [_row_to_record(row) for row in rows]
        except Exception as exc:
            raise MemoryUnavailableError(f"Memory list 失败: {exc}") from exc

    async def commit(
        self, memory_owner_id: str, mutations: list[MemoryMutation]
    ) -> list[MemoryRecord]:
        validated_mutations = [validate_mutation(mutation) for mutation in mutations]
        try:
            async with self._pool.connection() as conn:
                async with conn.transaction():
                    # 同一 owner 的 mutation 需要串行化：幂等检查与 user_memory
                    # 更新必须处于同一 owner 锁内，避免并发 replay 重复应用。
                    await conn.execute(
                        "SELECT pg_advisory_xact_lock(hashtext(%s))",
                        (memory_owner_id,),
                    )
                    changed: list[MemoryRecord] = []
                    for mutation in validated_mutations:
                        # mutation_id 的唯一性跨 owner 生效；先锁 mutation 再做查询，
                        # 使并发跨 owner 重用稳定落为 MemoryConflictError。
                        await conn.execute(
                            "SELECT pg_advisory_xact_lock(hashtext(%s))",
                            (mutation.mutation_id,),
                        )
                        existing_cur = await conn.execute(
                            "SELECT memory_owner_id, payload_json FROM memory_mutation"
                            " WHERE mutation_id = %s",
                            (mutation.mutation_id,),
                        )
                        existing_row = await existing_cur.fetchone()
                        if existing_row is not None:
                            if existing_row[0] != memory_owner_id:
                                raise MemoryConflictError("mutation_id 不能跨 memory owner 重用")
                            if not _mutation_matches(existing_row[1], mutation):
                                raise MemoryConflictError("同一 mutation_id 内容不一致")
                            continue
                        if mutation.operation is MemoryOperation.CLEAR_OWNER:
                            await conn.execute(
                                "UPDATE user_memory SET status = 'forgotten',"
                                " version = version + 1, updated_at = %s"
                                " WHERE memory_owner_id = %s AND status = 'active'",
                                (now_iso(), memory_owner_id),
                            )
                            await self._record_mutation(conn, memory_owner_id, mutation)
                            continue
                        if mutation.memory_key is None:
                            raise MemoryConflictError("记忆变更缺少 memory_key")
                        current_cur = await conn.execute(
                            "SELECT memory_id, memory_owner_id, memory_key, scope_key, value_json,"
                            " apply_mode, confidence, status, source_session_id, source_request_id,"
                            " version, created_at, updated_at, expires_at FROM user_memory"
                            " WHERE memory_owner_id = %s AND scope_key = %s AND memory_key = %s",
                            (memory_owner_id, mutation.scope_key, mutation.memory_key),
                        )
                        current_row = await current_cur.fetchone()
                        if mutation.operation is MemoryOperation.FORGET and current_row is None:
                            await self._record_mutation(conn, memory_owner_id, mutation)
                            continue
                        record = _record_for_mutation(memory_owner_id, mutation, current_row)
                        if mutation.operation is MemoryOperation.FORGET:
                            await conn.execute(
                                "UPDATE user_memory SET status = 'forgotten', version = %s,"
                                " updated_at = %s WHERE memory_id = %s",
                                (record.version, record.updated_at, record.memory_id),
                            )
                        else:
                            await conn.execute(
                                "INSERT INTO user_memory"
                                " (memory_id, memory_owner_id, memory_key, scope_key, value_json,"
                                " apply_mode, confidence, status, source_session_id,"
                                " source_request_id, version, created_at, updated_at, expires_at)"
                                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
                                " ON CONFLICT (memory_owner_id, scope_key, memory_key)"
                                " DO UPDATE SET value_json = EXCLUDED.value_json,"
                                " apply_mode = EXCLUDED.apply_mode,"
                                " confidence = EXCLUDED.confidence, status = EXCLUDED.status,"
                                " source_session_id = EXCLUDED.source_session_id,"
                                " source_request_id = EXCLUDED.source_request_id,"
                                " version = EXCLUDED.version, updated_at = EXCLUDED.updated_at,"
                                " expires_at = EXCLUDED.expires_at",
                                _record_params(record),
                            )
                        changed.append(record)
                        await self._record_mutation(conn, memory_owner_id, mutation)
                    return changed
        except MemoryConflictError:
            raise
        except Exception as exc:
            raise MemoryUnavailableError(f"Memory commit 失败: {exc}") from exc

    async def _record_mutation(self, conn: Any, owner: str, mutation: MemoryMutation) -> None:
        await conn.execute(
            "INSERT INTO memory_mutation"
            " (mutation_id, memory_owner_id, operation, payload_json, applied_at)"
            " VALUES (%s, %s, %s, %s, %s)",
            (
                mutation.mutation_id,
                owner,
                mutation.operation.value,
                json.dumps(mutation.model_dump(mode="json"), ensure_ascii=False),
                now_iso(),
            ),
        )

    async def clear_owner(self, memory_owner_id: str, mutation_id: str) -> None:
        mutation = MemoryMutation(
            mutation_id=mutation_id,
            operation=MemoryOperation.CLEAR_OWNER,
            source_session_id="memory-admin",
            source_request_id=mutation_id,
        )
        await self.commit(memory_owner_id, [mutation])


def _record_for_mutation(
    owner: str, mutation: MemoryMutation, current: tuple[Any, ...] | None
) -> MemoryRecord:
    now = now_iso()
    if mutation.operation is MemoryOperation.FORGET:
        if current is None:
            raise MemoryConflictError("不能遗忘不存在的记忆")
        current_record = _row_to_record(current)
        return current_record.model_copy(
            update={
                "status": MemoryStatus.FORGOTTEN,
                "version": current_record.version + 1,
                "updated_at": now,
            }
        )
    assert mutation.value is not None
    assert mutation.apply_mode is not None
    current_record = _row_to_record(current) if current is not None else None
    return MemoryRecord(
        memory_id=memory_id(owner, mutation.scope_key, mutation.memory_key or ""),
        memory_owner_id=owner,
        memory_key=mutation.memory_key or "",
        scope_key=mutation.scope_key,
        value=mutation.value,
        apply_mode=mutation.apply_mode,
        confidence=1.0,
        status=MemoryStatus.ACTIVE,
        source_session_id=mutation.source_session_id,
        source_request_id=mutation.source_request_id,
        version=(current_record.version + 1) if current_record is not None else 1,
        created_at=current_record.created_at if current_record is not None else now,
        updated_at=now,
    )


def _record_params(record: MemoryRecord) -> tuple[Any, ...]:
    return (
        record.memory_id,
        record.memory_owner_id,
        record.memory_key,
        record.scope_key,
        json.dumps(record.value, ensure_ascii=False),
        record.apply_mode.value,
        record.confidence,
        record.status.value,
        record.source_session_id,
        record.source_request_id,
        record.version,
        record.created_at,
        record.updated_at,
        record.expires_at,
    )
