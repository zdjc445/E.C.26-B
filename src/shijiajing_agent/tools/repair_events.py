"""从 Request Ledger/Memory 事务表补建一致性事件。"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sqlite3
import sys
import threading
from pathlib import Path
from typing import Any

from shijiajing_agent.adapters.event_store import (
    make_event_store_adapter,
    memory_event_attempt,
    same_event_content,
    stable_event_id,
)
from shijiajing_agent.asyncio_compat import run as run_async
from shijiajing_agent.contracts import AgentEventRecord, content_hash
from shijiajing_agent.tools.cli_support import configure_utf8_output, public_error_message

_LEDGER_SQL = (
    "SELECT session_id, request_id, response_json, response_hash, created_at "
    "FROM agent_request_result"
)
_MEMORY_SQL = (
    "SELECT mutation_id, memory_owner_id, operation, payload_hash, applied_at FROM memory_mutation"
)
_MEMORY_SOURCE_SQL = (
    "SELECT DISTINCT memory_owner_id, source_session_id, source_request_id "
    "FROM user_memory WHERE source_session_id <> '' AND source_request_id <> ''"
)
_EVENT_SQL = (
    "SELECT event_id, session_id, request_id, turn_id, trace_id, agent_name, node_name,"
    " event_type, status, input_hash, output_hash, state_version, payload_json, occurred_at"
    " FROM agent_event"
)


def _sqlite_path(dsn: str) -> Path:
    for prefix in ("sqlite:///", "sqlite://"):
        if dsn.startswith(prefix):
            dsn = dsn[len(prefix) :]
            break
    return Path(dsn)


def _fetch_rows(backend: str, dsn: str | None, query: str) -> list[tuple[Any, ...]]:
    if not dsn:
        return []
    if backend == "sqlite":
        path = _sqlite_path(dsn)
        if not path.exists():
            return []
        with sqlite3.connect(path) as conn:
            return conn.execute(query).fetchall()
    if backend == "postgres":
        import psycopg

        with psycopg.connect(dsn) as conn:
            with conn.cursor() as cursor:
                cursor_any: Any = cursor
                cursor_any.execute(query)
                return cursor_any.fetchall()
    raise ValueError(f"未知 repair source backend: {backend}")


def _candidate_events(
    ledger_dsn: str | None,
    memory_dsn: str | None,
    *,
    ledger_backend: str = "sqlite",
    memory_backend: str = "sqlite",
) -> list[AgentEventRecord]:
    candidates: list[AgentEventRecord] = []
    ledger_context: dict[tuple[str, str], tuple[str, str]] = {}
    for session_id, request_id, raw, response_hash, occurred_at in _fetch_rows(
        ledger_backend, ledger_dsn, _LEDGER_SQL
    ):
        response = json.loads(raw)
        turn_id = str(response["turn_id"])
        trace_id = str(response["trace_id"])
        ledger_context[(session_id, request_id)] = (turn_id, trace_id)
        event_id = stable_event_id(
            session_id,
            request_id,
            turn_id,
            "supervisor",
            None,
            "request_result_committed",
            0,
        )
        candidates.append(
            AgentEventRecord(
                event_id=event_id,
                session_id=session_id,
                request_id=request_id,
                turn_id=turn_id,
                trace_id=trace_id,
                agent_name="supervisor",
                node_name=None,
                event_type="request_result_committed",
                status=str(response["status"]),
                output_hash=response_hash,
                payload={"response_hash": response_hash},
                occurred_at=occurred_at,
            )
        )
    source_candidates: dict[str, set[tuple[str, str]]] = {}
    for owner, session_id, request_id in _fetch_rows(
        memory_backend, memory_dsn, _MEMORY_SOURCE_SQL
    ):
        source_candidates.setdefault(str(owner), set()).add((str(session_id), str(request_id)))
    for mutation_id, owner, operation, _payload_hash, occurred_at in _fetch_rows(
        memory_backend, memory_dsn, _MEMORY_SQL
    ):
        sources = source_candidates.get(str(owner), set())
        # 新版 mutation ledger 只保留 payload_hash，不足以反推出来源请求。
        # 只有 user_memory 能提供唯一来源时才修复，避免伪造 turn/trace。
        if len(sources) != 1:
            continue
        session_id, request_id = next(iter(sources))
        source = ledger_context.get((session_id, request_id))
        # 没有 Request Ledger 就没有真实 turn/trace，不能为 repair 猜测标识。
        if source is None:
            continue
        turn_id, trace_id = source
        event_type = (
            "memory_forgotten" if operation in {"forget", "clear_owner"} else "memory_committed"
        )
        event_id = stable_event_id(
            session_id,
            request_id,
            turn_id,
            "memory",
            "commit_memory",
            event_type,
            memory_event_attempt(mutation_id),
        )
        candidates.append(
            AgentEventRecord(
                event_id=event_id,
                session_id=session_id,
                request_id=request_id,
                turn_id=turn_id,
                trace_id=trace_id,
                agent_name="memory",
                node_name="commit_memory",
                event_type=event_type,
                status="success",
                output_hash=content_hash({"mutation_id": mutation_id}),
                payload={"mutation_id": mutation_id, "operation": operation},
                occurred_at=occurred_at,
            )
        )
    return candidates


def _existing_events(backend: str, dsn: str, event_ids: list[str]) -> dict[str, AgentEventRecord]:
    if not event_ids:
        return {}
    if backend == "sqlite":
        path = _sqlite_path(dsn)
        with sqlite3.connect(path) as conn:
            rows = conn.execute(
                _EVENT_SQL + " WHERE event_id IN (" + ",".join("?" for _ in event_ids) + ")",
                event_ids,
            ).fetchall()
            return {row[0]: _row_to_event(row) for row in rows}
    if backend == "postgres":
        import psycopg

        with psycopg.connect(dsn) as conn:
            with conn.cursor() as cursor:
                cursor_any: Any = cursor
                cursor_any.execute(
                    _EVENT_SQL + " WHERE event_id = ANY(%s)",
                    (event_ids,),
                )
                return {row[0]: _row_to_event(row) for row in cursor_any.fetchall()}
    raise ValueError(f"未知 event store backend: {backend}")


def _row_to_event(row: tuple[Any, ...]) -> AgentEventRecord:
    return AgentEventRecord(
        event_id=row[0],
        session_id=row[1],
        request_id=row[2],
        turn_id=row[3],
        trace_id=row[4],
        agent_name=row[5],
        node_name=row[6],
        event_type=row[7],
        status=row[8],
        input_hash=row[9],
        output_hash=row[10],
        state_version=row[11],
        payload=json.loads(row[12]),
        occurred_at=row[13],
    )


def _event_count(backend: str, dsn: str) -> int:
    if backend == "sqlite":
        with sqlite3.connect(_sqlite_path(dsn)) as conn:
            return int(conn.execute("SELECT COUNT(*) FROM agent_event").fetchone()[0])
    if backend == "postgres":
        import psycopg

        with psycopg.connect(dsn) as conn:
            with conn.cursor() as cursor:
                cursor_any: Any = cursor
                cursor_any.execute("SELECT COUNT(*) FROM agent_event")
                row = cursor_any.fetchone()
                if row is None:
                    raise ValueError("Event Store COUNT 查询没有返回结果")
                return int(row[0])
    raise ValueError(f"未知 event store backend: {backend}")


async def _append_events(backend: str, dsn: str, events: list[AgentEventRecord]) -> None:
    store = make_event_store_adapter(backend, dsn)
    try:
        await store.setup()
        for event in events:
            await store.append(event)
    finally:
        await store.close()


def _append_events_sync(backend: str, dsn: str, events: list[AgentEventRecord]) -> None:
    """CLI 也支持被 pytest/宿主事件循环内直接调用。"""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        run_async(_append_events(backend, dsn, events))
        return

    errors: list[BaseException] = []

    def run_in_thread() -> None:
        try:
            run_async(_append_events(backend, dsn, events))
        except BaseException as exc:
            errors.append(exc)

    thread = threading.Thread(target=run_in_thread)
    thread.start()
    thread.join()
    if errors:
        raise errors[0]


def main(argv: list[str] | None = None) -> int:
    configure_utf8_output()
    parser = argparse.ArgumentParser(prog="shijiajing-repair-events")
    parser.add_argument("--dsn", help="Event Store DSN")
    parser.add_argument("--event-store-backend", choices=("sqlite", "postgres"))
    parser.add_argument("--ledger-dsn", help="Request Ledger DSN")
    parser.add_argument(
        "--ledger-backend", choices=("sqlite", "postgres"), help="Request Ledger backend"
    )
    parser.add_argument("--memory-dsn", help="Memory DSN")
    parser.add_argument("--memory-backend", choices=("sqlite", "postgres"), help="Memory backend")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    if args.dry_run == args.apply:
        print("必须且只能指定 --dry-run 或 --apply", file=sys.stderr)
        return 2

    event_dsn = args.dsn or os.environ.get("SHIJIAJING_EVENT_STORE_DSN")
    if not event_dsn:
        print("未配置 SHIJIAJING_EVENT_STORE_DSN，未执行修复。")
        return 0
    event_backend = args.event_store_backend or os.environ.get(
        "SHIJIAJING_EVENT_STORE_BACKEND", "sqlite"
    )
    ledger_backend = args.ledger_backend or os.environ.get(
        "SHIJIAJING_REQUEST_LEDGER_BACKEND", "sqlite"
    )
    memory_backend = args.memory_backend or os.environ.get("SHIJIAJING_MEMORY_BACKEND", "sqlite")
    ledger_dsn = args.ledger_dsn or os.environ.get("SHIJIAJING_REQUEST_LEDGER_DSN")
    memory_dsn = args.memory_dsn or os.environ.get("SHIJIAJING_MEMORY_DSN")
    try:
        if event_backend == "sqlite" and not _sqlite_path(event_dsn).exists():
            raise ValueError(f"Event Store 文件不存在: {_sqlite_path(event_dsn)}")
        count = _event_count(event_backend, event_dsn)
        candidates = _candidate_events(
            ledger_dsn,
            memory_dsn,
            ledger_backend=ledger_backend,
            memory_backend=memory_backend,
        )
        existing = _existing_events(
            event_backend, event_dsn, [event.event_id for event in candidates]
        )
        conflicts = [
            event
            for event in candidates
            if event.event_id in existing
            and not same_event_content(existing[event.event_id], event)
        ]
        if conflicts:
            raise ValueError(
                "Event Store event_id 内容冲突: " + ", ".join(event.event_id for event in conflicts)
            )
        missing = [event for event in candidates if event.event_id not in existing]
        if args.apply and missing:
            _append_events_sync(event_backend, event_dsn, missing)
        action = "补建" if args.apply else "可补建"
        print(f"已检查 {count} 条事件；{action} {len(missing)} 条一致性事件。")
        return 0
    except Exception as exc:
        print(
            "事件修复失败："
            + public_error_message(exc, fallback="事件修复失败，请检查配置和事件存储"),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
