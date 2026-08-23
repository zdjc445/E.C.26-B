"""Checkpoint 适配器。

- ``SQLiteCheckpointAdapter``：开发环境，stdlib sqlite3，写操作经线程池执行不阻塞事件循环。
- ``PostgresCheckpointAdapter``：生产环境，psycopg async + 事务级 advisory lock + 乐观版本。

两种实现共享同一张逻辑表 ``agent_checkpoint(session_id, state_json, state_version,
schema_version, saved_at)``。状态序列化把 pydantic 模型 dump 成 JSON；加载时按字段
类型重建模型实例（facade 与节点依赖 ``current_request`` / ``response`` / ``image_ref``
等为模型实例）。``evidence_bundle`` 是纯 dataclass，同样重建。

- §17.1：``schema_version`` 不兼容时拒绝加载，必须显式 migration。
- 保存采用乐观版本检查；冲突抛 ``SessionConflictError``（advisory lock 只用于
  生产 Postgres，开发 SQLite 由进程内锁串行化，不同 session 不受影响）。
- ``previous_state`` 不持久化（§7.3：只由 facade 注入，避免状态无限膨胀）。
- Checkpoint 失败必须阻断成功提交（facade 转为失败响应），不静默丢弃。
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import sqlite3
import threading
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, cast

from pydantic import BaseModel

from shijiajing_agent.config import Settings
from shijiajing_agent.contracts import (
    AgentExecutionContext,
    AgentInterrupt,
    AgentRequest,
    AgentResponse,
    AgentResult,
    Clarification,
    CompletionReason,
    ConversationTurnSummary,
    ImageRef,
    IntentPatch,
    MatchPair,
    MemoryMutation,
    MemoryRecord,
    NormalizedCandidate,
    RankedGroup,
    RecognitionResult,
    RetrievalCandidate,
    RetrievalQuery,
    ShoppingConstraints,
    SkuGroup,
)
from shijiajing_agent.domain.evidence import EvidenceBundle, GroupEvidence
from shijiajing_agent.errors import CheckpointUnavailableError, SessionConflictError
from shijiajing_agent.persistence_safety import sanitize_persisted_value
from shijiajing_agent.ports.checkpoint import CheckpointPort
from shijiajing_agent.state import SCHEMA_VERSION, AgentState

# 单值 pydantic 模型字段：加载时重建实例（None 时置 None）
_SINGLE_MODEL_FIELDS: dict[str, type[BaseModel]] = {
    "execution_context": AgentExecutionContext,
    "active_interrupt": AgentInterrupt,
    "current_request": AgentRequest,
    "image_ref": ImageRef,
    "recognition": RecognitionResult,
    "intent_patch": IntentPatch,
    "effective_constraints": ShoppingConstraints,
    "retrieval_query": RetrievalQuery,
    "clarification": Clarification,
    "response": AgentResponse,
}

# 列表 pydantic 模型字段
_LIST_MODEL_FIELDS: dict[str, type[BaseModel]] = {
    "recent_turns": ConversationTurnSummary,
    "memory_context": MemoryRecord,
    "pending_memory_mutations": MemoryMutation,
    "agent_results": AgentResult,
    "recognition_history": RecognitionResult,
    "candidates": RetrievalCandidate,
    "normalized_candidates": NormalizedCandidate,
    "sku_groups": SkuGroup,
    "ranked_groups": RankedGroup,
    "same_item_review_pairs": MatchPair,
}

# StrEnum 字段：加载时按值重建
_ENUM_FIELDS: dict[str, type[StrEnum]] = {"completion_reason": CompletionReason}


def _to_jsonable(value: Any) -> Any:
    """pydantic 模型 / dataclass / Enum → JSON 原语（递归）。"""
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return _to_jsonable(dataclasses.asdict(value))
    if isinstance(value, dict):
        mapping = cast(dict[str, Any], value)
        return {k: _to_jsonable(v) for k, v in mapping.items()}
    if isinstance(value, (list, tuple)):
        seq = cast(list[Any], value)
        return [_to_jsonable(v) for v in seq]
    if isinstance(value, StrEnum):
        return value.value
    return value


def _state_to_payload(state: AgentState) -> dict[str, Any]:
    """持久化前清洗：剔除 previous_state、原始请求和自由文本输入。"""
    safe_state = sanitize_persisted_value({k: v for k, v in state.items() if k != "previous_state"})
    return {k: _to_jsonable(v) for k, v in cast(dict[str, Any], safe_state).items()}


def _state_from_payload(payload: dict[str, Any]) -> AgentState:
    """按字段类型重建模型/dataclass/Enum 实例；TypedDict 记录字段原样透传。"""
    out: dict[str, Any] = {}
    for key, value in payload.items():
        model = _SINGLE_MODEL_FIELDS.get(key)
        if model is not None:
            instance = model.model_validate(value) if value is not None else None
            out[key] = sanitize_persisted_value(instance)
            continue
        model = _LIST_MODEL_FIELDS.get(key)
        if model is not None:
            items = cast(list[Any], value or [])
            out[key] = [sanitize_persisted_value(model.model_validate(item)) for item in items]
            continue
        if key == "evidence_bundle":
            out[key] = _evidence_from_jsonable(value)
            continue
        enum_cls = _ENUM_FIELDS.get(key)
        if enum_cls is not None:
            out[key] = enum_cls(value) if value is not None else None
            continue
        out[key] = value
    return AgentState(**out)


def _evidence_from_jsonable(value: Any) -> EvidenceBundle | None:
    if value is None:
        return None
    payload = cast(dict[str, Any], value)
    raw_groups = cast(list[Any], payload.get("groups") or [])
    groups = [GroupEvidence(**cast(dict[str, Any], g)) for g in raw_groups]
    raw_notices = cast(list[Any], payload.get("notices") or [])
    notices = [str(n) for n in raw_notices]
    return EvidenceBundle(
        query_summary=str(payload.get("query_summary") or ""),
        groups=groups,
        notices=notices,
    )


_DDL = """
CREATE TABLE IF NOT EXISTS agent_checkpoint (
    session_id     TEXT PRIMARY KEY,
    state_json     TEXT NOT NULL,
    state_version  INTEGER NOT NULL,
    schema_version TEXT NOT NULL,
    saved_at       TEXT NOT NULL
)

"""
_RESUME_DDL = """
CREATE TABLE IF NOT EXISTS agent_resume_claim (
    session_id  TEXT NOT NULL,
    interrupt_id TEXT NOT NULL,
    claimed_at  TEXT NOT NULL,
    PRIMARY KEY (session_id, interrupt_id)
)
"""


class SQLiteCheckpointAdapter:
    """开发环境 Checkpoint（stdlib sqlite3，线程池执行，不阻塞事件循环）。"""

    def __init__(self, dsn: str) -> None:
        path = dsn
        for prefix in ("sqlite:///", "sqlite://"):
            if path.startswith(prefix):
                path = path[len(prefix) :]
                break
        if not path:
            raise ValueError("SHIJIAJING_CHECKPOINT_DSN 不能为空")
        self._path = path
        self._lock = threading.Lock()
        self._conn: sqlite3.Connection | None = None
        self._closed = False

    def _connect(self) -> sqlite3.Connection:
        if self._conn is None:
            conn = sqlite3.connect(self._path, check_same_thread=False)
            conn.execute(_DDL)
            conn.execute(_RESUME_DDL)
            conn.commit()
            self._conn = conn
        return self._conn

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None
            self._closed = True

    async def setup(self) -> None:
        await asyncio.to_thread(self._setup_sync)

    def _setup_sync(self) -> None:
        with self._lock:
            if self._closed:
                raise CheckpointUnavailableError("Checkpoint adapter 已关闭")
            self._connect()

    # ------------------------------------------------------------------
    async def load(self, session_id: str) -> tuple[AgentState, int] | None:
        return await asyncio.to_thread(self._load_sync, session_id)

    async def save(self, session_id: str, state: AgentState, expected_version: int | None) -> int:
        return await asyncio.to_thread(self._save_sync, session_id, state, expected_version)

    async def claim_resume(self, session_id: str, interrupt_id: str) -> bool:
        return await asyncio.to_thread(self._claim_resume_sync, session_id, interrupt_id)

    async def release_resume(self, session_id: str, interrupt_id: str) -> None:
        await asyncio.to_thread(self._release_resume_sync, session_id, interrupt_id)

    # ------------------------------------------------------------------
    def _load_sync(self, session_id: str) -> tuple[AgentState, int] | None:
        with self._lock:
            if self._closed:
                raise CheckpointUnavailableError("Checkpoint adapter 已关闭")
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT state_json, state_version, schema_version"
                    " FROM agent_checkpoint WHERE session_id = ?",
                    (session_id,),
                ).fetchone()
            except sqlite3.Error as exc:
                raise CheckpointUnavailableError(f"checkpoint 读取失败: {exc}") from exc
            if row is None:
                return None
            state_json, version, stored_schema = row
            if stored_schema not in {SCHEMA_VERSION, "1.0"}:
                raise CheckpointUnavailableError(
                    f"Checkpoint schema 版本不兼容：存储 {stored_schema}，"
                    f"当前 {SCHEMA_VERSION}，需显式迁移"
                )
            try:
                payload = json.loads(state_json)
            except json.JSONDecodeError as exc:
                raise CheckpointUnavailableError(f"checkpoint 数据损坏: {exc}") from exc
            payload = migrate_state_payload(payload, stored_schema)
            return _state_from_payload(payload), int(version)

    def _save_sync(self, session_id: str, state: AgentState, expected_version: int | None) -> int:
        with self._lock:
            if self._closed:
                raise CheckpointUnavailableError("Checkpoint adapter 已关闭")
            conn = self._connect()
            try:
                conn.execute("BEGIN IMMEDIATE")
                row = conn.execute(
                    "SELECT state_version FROM agent_checkpoint WHERE session_id = ?",
                    (session_id,),
                ).fetchone()
                stored = int(row[0]) if row else 0
                if expected_version is not None and stored != expected_version:
                    conn.rollback()
                    raise SessionConflictError(
                        f"乐观版本冲突：期望 {expected_version}，实际 {stored}"
                    )
                new_version = stored + 1
                # §17：state_version 由 Checkpoint 维护，随状态一起持久化
                state["state_version"] = new_version
                conn.execute(
                    "INSERT INTO agent_checkpoint"
                    " (session_id, state_json, state_version, schema_version, saved_at)"
                    " VALUES (?, ?, ?, ?, ?)"
                    " ON CONFLICT(session_id) DO UPDATE SET"
                    " state_json = excluded.state_json,"
                    " state_version = excluded.state_version,"
                    " schema_version = excluded.schema_version,"
                    " saved_at = excluded.saved_at",
                    (
                        session_id,
                        json.dumps(_state_to_payload(state), ensure_ascii=False),
                        new_version,
                        SCHEMA_VERSION,
                        datetime.now(UTC).isoformat(),
                    ),
                )
                conn.commit()
            except sqlite3.Error as exc:
                conn.rollback()
                raise CheckpointUnavailableError(f"checkpoint 写入失败: {exc}") from exc
            return new_version

    def _claim_resume_sync(self, session_id: str, interrupt_id: str) -> bool:
        with self._lock:
            if self._closed:
                raise CheckpointUnavailableError("Checkpoint adapter 已关闭")
            conn = self._connect()
            try:
                cursor = conn.execute(
                    "INSERT OR IGNORE INTO agent_resume_claim"
                    " (session_id, interrupt_id, claimed_at) VALUES (?, ?, ?)",
                    (session_id, interrupt_id, datetime.now(UTC).isoformat()),
                )
                conn.commit()
                return cursor.rowcount == 1
            except sqlite3.Error as exc:
                conn.rollback()
                raise CheckpointUnavailableError(f"resume fence 写入失败: {exc}") from exc

    def _release_resume_sync(self, session_id: str, interrupt_id: str) -> None:
        with self._lock:
            if self._closed:
                raise CheckpointUnavailableError("Checkpoint adapter 已关闭")
            conn = self._connect()
            try:
                conn.execute(
                    "DELETE FROM agent_resume_claim WHERE session_id = ? AND interrupt_id = ?",
                    (session_id, interrupt_id),
                )
                conn.commit()
            except sqlite3.Error as exc:
                conn.rollback()
                raise CheckpointUnavailableError(f"resume fence 释放失败: {exc}") from exc


_PG_DDL = """
CREATE TABLE IF NOT EXISTS agent_checkpoint (
    session_id     TEXT PRIMARY KEY,
    state_json     TEXT NOT NULL,
    state_version  BIGINT NOT NULL,
    schema_version TEXT NOT NULL,
    saved_at       TIMESTAMPTZ NOT NULL
)
"""
_PG_RESUME_DDL = """
CREATE TABLE IF NOT EXISTS agent_resume_claim (
    session_id  TEXT NOT NULL,
    interrupt_id TEXT NOT NULL,
    claimed_at  TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (session_id, interrupt_id)
)
"""


def migrate_state_payload(payload: dict[str, Any], stored_schema: str) -> dict[str, Any]:
    """纯函数迁移 legacy 1.0 payload 到 1.1；不修改输入对象。"""
    if stored_schema == SCHEMA_VERSION:
        return dict(payload)
    if stored_schema != "1.0":
        raise CheckpointUnavailableError(
            f"Checkpoint schema 版本不兼容：存储 {stored_schema}，当前 {SCHEMA_VERSION}，需显式迁移"
        )
    migrated = dict(payload)
    migrated.pop("previous_state", None)
    migrated.setdefault("execution_context", None)
    migrated.setdefault("recent_turns", [])
    migrated.setdefault("memory_context", [])
    migrated.setdefault("pending_memory_mutations", [])
    migrated.setdefault("same_item_review_pairs", [])
    migrated.setdefault("agent_results", [])
    migrated.setdefault("active_interrupt", None)
    migrated.setdefault("resume_consumed", False)
    migrated.setdefault("interrupt_generation", 0)
    migrated.setdefault("fusion_version", None)
    migrated.setdefault("rerank_version", None)
    migrated.setdefault("retrieval_index_version", None)
    migrated["schema_version"] = SCHEMA_VERSION
    return migrated


class PostgresCheckpointAdapter:
    """生产环境 Checkpoint（psycopg async + 事务级 advisory lock + 乐观版本）。

    同一 session 的并发写由 ``pg_advisory_xact_lock(hashtext(session_id))`` 在事务内
    串行化；不同 session 互不阻塞。版本冲突或任何数据库错误都回滚事务。
    """

    def __init__(
        self,
        dsn: str,
        *,
        max_size: int = 4,
        min_size: int = 1,
        timeout_seconds: float = 30.0,
    ) -> None:
        if not dsn:
            raise ValueError("SHIJIAJING_CHECKPOINT_DSN 不能为空")
        self._dsn = dsn
        self._pool = self._build_pool(dsn, max_size, min_size, timeout_seconds)
        self._ddl_done = False

    @staticmethod
    def _build_pool(dsn: str, max_size: int, min_size: int, timeout_seconds: float) -> Any:
        # psycopg 为可选依赖（pyproject `postgres` extra），仅构造该适配器时导入
        from psycopg_pool import AsyncConnectionPool

        return AsyncConnectionPool(
            dsn,
            min_size=min_size,
            max_size=max_size,
            timeout=timeout_seconds,
            open=False,
        )

    async def _ready(self) -> Any:
        pool = self._pool
        if pool is None:
            raise CheckpointUnavailableError("Checkpoint adapter 已关闭")
        if pool.closed:
            await pool.open()
        if not self._ddl_done:
            async with pool.connection() as conn:
                await conn.execute(_PG_DDL)
                await conn.execute(_PG_RESUME_DDL)
            self._ddl_done = True
        return pool

    async def setup(self) -> None:
        await self._ready()

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def claim_resume(self, session_id: str, interrupt_id: str) -> bool:
        try:
            pool = await self._ready()
            async with pool.connection() as conn:
                async with conn.transaction():
                    cursor = await conn.execute(
                        "INSERT INTO agent_resume_claim"
                        " (session_id, interrupt_id, claimed_at) VALUES (%s, %s, %s)"
                        " ON CONFLICT (session_id, interrupt_id) DO NOTHING",
                        (session_id, interrupt_id, datetime.now(UTC)),
                    )
                    return cursor.rowcount == 1
        except Exception as exc:
            raise CheckpointUnavailableError(f"resume fence 写入失败: {exc}") from exc

    async def release_resume(self, session_id: str, interrupt_id: str) -> None:
        try:
            pool = await self._ready()
            async with pool.connection() as conn:
                async with conn.transaction():
                    await conn.execute(
                        "DELETE FROM agent_resume_claim"
                        " WHERE session_id = %s AND interrupt_id = %s",
                        (session_id, interrupt_id),
                    )
        except Exception as exc:
            raise CheckpointUnavailableError(f"resume fence 释放失败: {exc}") from exc

    # ------------------------------------------------------------------
    async def load(self, session_id: str) -> tuple[AgentState, int] | None:
        try:
            pool = await self._ready()
            async with pool.connection() as conn:
                row = await (
                    await conn.execute(
                        "SELECT state_json, state_version, schema_version"
                        " FROM agent_checkpoint WHERE session_id = %s",
                        (session_id,),
                    )
                ).fetchone()
        except CheckpointUnavailableError:
            raise
        except Exception as exc:
            raise CheckpointUnavailableError(f"checkpoint 读取失败: {exc}") from exc
        if row is None:
            return None
        state_json, version, stored_schema = row
        if stored_schema not in {SCHEMA_VERSION, "1.0"}:
            raise CheckpointUnavailableError(
                f"Checkpoint schema 版本不兼容：存储 {stored_schema}，"
                f"当前 {SCHEMA_VERSION}，需显式迁移"
            )
        try:
            payload = json.loads(state_json)
        except json.JSONDecodeError as exc:
            raise CheckpointUnavailableError(f"checkpoint 数据损坏: {exc}") from exc
        payload = migrate_state_payload(payload, stored_schema)
        return _state_from_payload(payload), int(version)

    async def save(self, session_id: str, state: AgentState, expected_version: int | None) -> int:
        try:
            pool = await self._ready()
            async with pool.connection() as conn:
                async with conn.transaction():
                    await conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (session_id,))
                    row = await (
                        await conn.execute(
                            "SELECT state_version FROM agent_checkpoint WHERE session_id = %s",
                            (session_id,),
                        )
                    ).fetchone()
                    stored = int(row[0]) if row else 0
                    if expected_version is not None and stored != expected_version:
                        raise SessionConflictError(
                            f"乐观版本冲突：期望 {expected_version}，实际 {stored}"
                        )
                    new_version = stored + 1
                    # §17：state_version 由 Checkpoint 维护，随状态一起持久化
                    state["state_version"] = new_version
                    await conn.execute(
                        "INSERT INTO agent_checkpoint"
                        " (session_id, state_json, state_version, schema_version, saved_at)"
                        " VALUES (%s, %s, %s, %s, %s)"
                        " ON CONFLICT (session_id) DO UPDATE SET"
                        " state_json = EXCLUDED.state_json,"
                        " state_version = EXCLUDED.state_version,"
                        " schema_version = EXCLUDED.schema_version,"
                        " saved_at = EXCLUDED.saved_at",
                        (
                            session_id,
                            json.dumps(_state_to_payload(state), ensure_ascii=False),
                            new_version,
                            SCHEMA_VERSION,
                            datetime.now(UTC),
                        ),
                    )
        except SessionConflictError:
            raise
        except Exception as exc:
            raise CheckpointUnavailableError(f"checkpoint 写入失败: {exc}") from exc
        return new_version


def make_checkpoint(settings: Settings) -> CheckpointPort:
    """按配置构建 Checkpoint 适配器（sqlite / postgres）。"""
    dsn = settings.checkpoint_dsn or ""
    backend = (settings.checkpoint_backend or "sqlite").lower()
    if backend == "sqlite":
        return SQLiteCheckpointAdapter(dsn)
    if backend == "postgres":
        return PostgresCheckpointAdapter(
            dsn,
            min_size=settings.postgres_pool_min_size,
            max_size=settings.postgres_pool_max_size,
            timeout_seconds=settings.postgres_pool_timeout_seconds,
        )
    raise ValueError(f"未知 checkpoint_backend: {backend}（支持 sqlite / postgres）")
