"""SQLite 和内存版本缓存；缓存故障由上层转为 miss。"""

from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import sqlite3
import threading
from datetime import UTC, datetime, timedelta
from typing import Any

import orjson

from shijiajing_agent.errors import CacheUnavailableError
from shijiajing_agent.persistence_safety import sanitize_cache_value

_DDL = """
CREATE TABLE IF NOT EXISTS versioned_cache (
    namespace TEXT NOT NULL,
    cache_key TEXT NOT NULL,
    value_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    PRIMARY KEY(namespace, cache_key)
)
"""


def canonical_cache_key(value: Any) -> str:
    raw = orjson.dumps(value, option=orjson.OPT_SORT_KEYS)
    return hashlib.sha256(raw).hexdigest()


class DisabledVersionedCache:
    async def setup(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def get(self, namespace: str, key: str) -> dict[str, Any] | None:
        del namespace, key
        return None

    async def set(self, namespace: str, key: str, value: dict[str, Any], ttl_seconds: int) -> None:
        del namespace, key, value, ttl_seconds

    async def delete_namespace(self, namespace: str) -> None:
        del namespace


class InMemoryVersionedCache:
    def __init__(self) -> None:
        self._values: dict[tuple[str, str], tuple[dict[str, Any], datetime]] = {}
        self._lock = asyncio.Lock()

    async def setup(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def get(self, namespace: str, key: str) -> dict[str, Any] | None:
        async with self._lock:
            item = self._values.get((namespace, key))
            if item is None:
                return None
            value, expires_at = item
            if expires_at <= datetime.now(UTC):
                self._values.pop((namespace, key), None)
                return None
            return copy.deepcopy(value)

    async def set(self, namespace: str, key: str, value: dict[str, Any], ttl_seconds: int) -> None:
        if ttl_seconds < 1:
            raise ValueError("ttl_seconds 必须大于 0")
        async with self._lock:
            self._values[(namespace, key)] = (
                sanitize_cache_value(value, namespace=namespace),
                datetime.now(UTC) + timedelta(seconds=ttl_seconds),
            )

    async def delete_namespace(self, namespace: str) -> None:
        async with self._lock:
            for key in [k for k in self._values if k[0] == namespace]:
                self._values.pop(key, None)


class SQLiteVersionedCacheAdapter:
    def __init__(self, dsn: str) -> None:
        path = dsn
        for prefix in ("sqlite:///", "sqlite://"):
            if path.startswith(prefix):
                path = path[len(prefix) :]
                break
        if not path:
            raise ValueError("SHIJIAJING_CACHE_DSN 不能为空")
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
                raise CacheUnavailableError("Cache adapter 已关闭")
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

    async def get(self, namespace: str, key: str) -> dict[str, Any] | None:
        return await asyncio.to_thread(self._get_sync, namespace, key)

    def _get_sync(self, namespace: str, key: str) -> dict[str, Any] | None:
        with self._lock:
            try:
                row = (
                    self._connect()
                    .execute(
                        "SELECT value_json, expires_at FROM versioned_cache"
                        " WHERE namespace = ? AND cache_key = ?",
                        (namespace, key),
                    )
                    .fetchone()
                )
                if row is None:
                    return None
                if datetime.fromisoformat(row[1]) <= datetime.now(UTC):
                    self._connect().execute(
                        "DELETE FROM versioned_cache WHERE namespace = ? AND cache_key = ?",
                        (namespace, key),
                    )
                    self._connect().commit()
                    return None
                return json.loads(row[0])
            except Exception as exc:
                raise CacheUnavailableError(f"Cache 读取失败: {exc}") from exc

    async def set(self, namespace: str, key: str, value: dict[str, Any], ttl_seconds: int) -> None:
        await asyncio.to_thread(self._set_sync, namespace, key, value, ttl_seconds)

    def _set_sync(self, namespace: str, key: str, value: dict[str, Any], ttl_seconds: int) -> None:
        if ttl_seconds < 1:
            raise ValueError("ttl_seconds 必须大于 0")
        created = datetime.now(UTC)
        expires = created + timedelta(seconds=ttl_seconds)
        safe_value = sanitize_cache_value(value, namespace=namespace)
        with self._lock:
            try:
                self._connect().execute(
                    "INSERT INTO versioned_cache"
                    " (namespace, cache_key, value_json, created_at, expires_at)"
                    " VALUES (?, ?, ?, ?, ?)"
                    " ON CONFLICT(namespace, cache_key) DO UPDATE SET"
                    " value_json=excluded.value_json, created_at=excluded.created_at,"
                    " expires_at=excluded.expires_at",
                    (
                        namespace,
                        key,
                        json.dumps(safe_value, ensure_ascii=False, sort_keys=True),
                        created.isoformat(),
                        expires.isoformat(),
                    ),
                )
                self._connect().commit()
            except Exception as exc:
                raise CacheUnavailableError(f"Cache 写入失败: {exc}") from exc

    async def delete_namespace(self, namespace: str) -> None:
        await asyncio.to_thread(self._delete_sync, namespace)

    def _delete_sync(self, namespace: str) -> None:
        with self._lock:
            try:
                self._connect().execute(
                    "DELETE FROM versioned_cache WHERE namespace = ?", (namespace,)
                )
                self._connect().commit()
            except Exception as exc:
                raise CacheUnavailableError(f"Cache 删除失败: {exc}") from exc


def make_cache_adapter(
    backend: str,
    dsn: str | None,
    *,
    pool_min_size: int = 1,
    pool_max_size: int = 4,
    pool_timeout_seconds: float = 30.0,
) -> Any:
    normalized = backend.lower()
    if normalized == "disabled":
        return DisabledVersionedCache()
    if normalized == "sqlite":
        return SQLiteVersionedCacheAdapter(dsn or "")
    if normalized == "memory":
        return InMemoryVersionedCache()
    if normalized == "postgres":
        return PostgresVersionedCacheAdapter(
            dsn or "",
            min_size=pool_min_size,
            max_size=pool_max_size,
            timeout_seconds=pool_timeout_seconds,
        )
    raise ValueError(f"未知 cache_backend: {backend}")


class PostgresVersionedCacheAdapter:
    """PostgreSQL TTL cache；缓存读写失败由上层按 miss 处理。"""

    def __init__(
        self,
        dsn: str,
        *,
        max_size: int = 4,
        min_size: int = 1,
        timeout_seconds: float = 30.0,
    ) -> None:
        if not dsn:
            raise ValueError("SHIJIAJING_CACHE_DSN 不能为空")
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
                    await conn.execute(_DDL.replace("?", "%s"))
        except Exception as exc:
            raise CacheUnavailableError(f"Cache setup 失败: {exc}") from exc

    async def close(self) -> None:
        await self._pool.close()

    async def get(self, namespace: str, key: str) -> dict[str, Any] | None:
        try:
            async with self._pool.connection() as conn:
                cur = await conn.execute(
                    "SELECT value_json, expires_at FROM versioned_cache"
                    " WHERE namespace = %s AND cache_key = %s",
                    (namespace, key),
                )
                row = await cur.fetchone()
                if row is None:
                    return None
                if datetime.fromisoformat(row[1]) <= datetime.now(UTC):
                    await conn.execute(
                        "DELETE FROM versioned_cache WHERE namespace = %s AND cache_key = %s",
                        (namespace, key),
                    )
                    return None
                return json.loads(row[0])
        except Exception as exc:
            raise CacheUnavailableError(f"Cache 读取失败: {exc}") from exc

    async def set(self, namespace: str, key: str, value: dict[str, Any], ttl_seconds: int) -> None:
        if ttl_seconds < 1:
            raise ValueError("ttl_seconds 必须大于 0")
        created = datetime.now(UTC)
        expires = created + timedelta(seconds=ttl_seconds)
        safe_value = sanitize_cache_value(value, namespace=namespace)
        try:
            async with self._pool.connection() as conn:
                await conn.execute(
                    "INSERT INTO versioned_cache"
                    " (namespace, cache_key, value_json, created_at, expires_at)"
                    " VALUES (%s, %s, %s, %s, %s)"
                    " ON CONFLICT(namespace, cache_key) DO UPDATE SET"
                    " value_json = EXCLUDED.value_json, created_at = EXCLUDED.created_at,"
                    " expires_at = EXCLUDED.expires_at",
                    (
                        namespace,
                        key,
                        json.dumps(safe_value, ensure_ascii=False, sort_keys=True),
                        created.isoformat(),
                        expires.isoformat(),
                    ),
                )
        except Exception as exc:
            raise CacheUnavailableError(f"Cache 写入失败: {exc}") from exc

    async def delete_namespace(self, namespace: str) -> None:
        try:
            async with self._pool.connection() as conn:
                await conn.execute("DELETE FROM versioned_cache WHERE namespace = %s", (namespace,))
        except Exception as exc:
            raise CacheUnavailableError(f"Cache 删除失败: {exc}") from exc
