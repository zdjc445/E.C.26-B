"""legacy checkpoint 1.0 -> 1.1 的 inspect/validate CLI。"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any

from shijiajing_agent.adapters.checkpoint import migrate_state_payload
from shijiajing_agent.adapters.event_store import make_event_store_adapter, stable_event_id
from shijiajing_agent.asyncio_compat import run as run_async
from shijiajing_agent.contracts import AgentEventRecord, now_iso
from shijiajing_agent.state import SCHEMA_VERSION
from shijiajing_agent.tools.cli_support import configure_utf8_output, public_error_message

_MIGRATION_AUDIT_DDL = """
CREATE TABLE IF NOT EXISTS checkpoint_migration_audit (
    session_id TEXT PRIMARY KEY,
    state_version INTEGER NOT NULL,
    request_id TEXT,
    turn_id TEXT,
    trace_id TEXT,
    from_schema TEXT NOT NULL,
    to_schema TEXT NOT NULL,
    migrated_at TEXT NOT NULL
)
"""


def _args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="shijiajing-migrate-state")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("inspect", "validate", "migrate"):
        command = sub.add_parser(name)
        command.add_argument("--dsn", help="SQLite checkpoint 文件路径")
        if name == "migrate":
            command.add_argument(
                "--apply",
                action="store_true",
                help="提交 legacy 1.0 -> 1.1 的 SQLite 更新；默认只预览",
            )
            command.add_argument(
                "--event-store-backend",
                choices=("sqlite", "postgres"),
                help="写入 checkpoint_migrated 的 Event Store backend",
            )
            command.add_argument("--event-store-dsn", help="checkpoint_migrated 的 Event Store DSN")
    return parser.parse_args(argv)


def _path(dsn: str) -> str:
    for prefix in ("sqlite:///", "sqlite://"):
        if dsn.startswith(prefix):
            return dsn[len(prefix) :]
    return dsn


def _read_rows(path: str) -> list[tuple[Any, ...]]:
    db = Path(path)
    if not db.exists():
        raise ValueError(f"checkpoint 文件不存在: {db}")
    conn = sqlite3.connect(db)
    try:
        return conn.execute(
            "SELECT session_id, state_json, state_version, schema_version"
            " FROM agent_checkpoint ORDER BY session_id"
        ).fetchall()
    finally:
        conn.close()


def _migration_candidates(rows: list[tuple[Any, ...]]) -> tuple[list[dict[str, Any]], list[str]]:
    candidates: list[dict[str, Any]] = []
    invalid: list[str] = []
    for session_id, raw, state_version, schema in rows:
        if schema != "1.0":
            continue
        try:
            payload = json.loads(raw)
            migrated = migrate_state_payload(payload, schema)
            candidates.append(
                {
                    "session_id": str(session_id),
                    "state_json": json.dumps(migrated, ensure_ascii=False),
                    "state_version": int(state_version),
                    "request_id": payload.get("request_id"),
                    "turn_id": payload.get("turn_id"),
                    "trace_id": payload.get("trace_id"),
                }
            )
        except Exception:
            invalid.append(str(session_id))
    return candidates, invalid


def _apply_migrations(path: str, candidates: list[dict[str, Any]]) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(_MIGRATION_AUDIT_DDL)
        for item in candidates:
            conn.execute(
                "UPDATE agent_checkpoint SET state_json = ?, schema_version = ?"
                " WHERE session_id = ? AND schema_version = ?",
                (item["state_json"], SCHEMA_VERSION, item["session_id"], "1.0"),
            )
            conn.execute(
                "INSERT OR IGNORE INTO checkpoint_migration_audit"
                " (session_id, state_version, request_id, turn_id, trace_id,"
                " from_schema, to_schema, migrated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    item["session_id"],
                    item["state_version"],
                    item.get("request_id"),
                    item.get("turn_id"),
                    item.get("trace_id"),
                    "1.0",
                    SCHEMA_VERSION,
                    now_iso(),
                ),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _read_migration_audit(path: str) -> list[dict[str, Any]]:
    conn = sqlite3.connect(path)
    try:
        try:
            rows = conn.execute(
                "SELECT session_id, state_version, request_id, turn_id, trace_id"
                " FROM checkpoint_migration_audit ORDER BY session_id"
            ).fetchall()
        except sqlite3.OperationalError:
            return []
        return [
            {
                "session_id": str(session_id),
                "state_version": int(state_version),
                "request_id": request_id,
                "turn_id": turn_id,
                "trace_id": trace_id,
            }
            for session_id, state_version, request_id, turn_id, trace_id in rows
        ]
    finally:
        conn.close()


def _migration_events(candidates: list[dict[str, Any]]) -> tuple[list[AgentEventRecord], int]:
    events: list[AgentEventRecord] = []
    skipped = 0
    for item in candidates:
        request_id = item.get("request_id")
        turn_id = item.get("turn_id")
        trace_id = item.get("trace_id")
        if (
            not isinstance(request_id, str)
            or not request_id
            or not isinstance(turn_id, str)
            or not turn_id
            or not isinstance(trace_id, str)
            or not trace_id
        ):
            skipped += 1
            continue
        events.append(
            AgentEventRecord(
                event_id=stable_event_id(
                    item["session_id"],
                    request_id,
                    turn_id,
                    "checkpoint",
                    None,
                    "checkpoint_migrated",
                    item["state_version"],
                ),
                session_id=item["session_id"],
                request_id=request_id,
                turn_id=turn_id,
                trace_id=trace_id,
                agent_name="checkpoint",
                node_name=None,
                event_type="checkpoint_migrated",
                status="success",
                state_version=item["state_version"],
                payload={"from_schema": "1.0", "to_schema": SCHEMA_VERSION},
                occurred_at=now_iso(),
            )
        )
    return events, skipped


async def _append_migration_events(backend: str, dsn: str, events: list[AgentEventRecord]) -> None:
    store = make_event_store_adapter(backend, dsn)
    await store.setup()
    try:
        for event in events:
            await store.append(event)
    finally:
        await store.close()


def main(argv: list[str] | None = None) -> int:
    configure_utf8_output()
    args = _args(argv)
    try:
        dsn = args.dsn or os.environ.get("SHIJIAJING_CHECKPOINT_DSN")
        if not dsn:
            print("未配置 SHIJIAJING_CHECKPOINT_DSN，未执行迁移检查。")
            return 0
        rows = _read_rows(_path(dsn))
        versions: dict[str, int] = {}
        invalid: list[str] = []
        for _session_id, _raw, _version, schema in rows:
            versions[schema] = versions.get(schema, 0) + 1
        candidates, migration_invalid = _migration_candidates(rows)
        if args.command in {"validate", "migrate"}:
            invalid.extend(migration_invalid)
        print(json.dumps({"rows": len(rows), "schema_versions": versions}, ensure_ascii=False))
        if invalid:
            print(
                json.dumps({"invalid_sessions": invalid}, ensure_ascii=False),
                file=sys.stderr,
            )
            return 1
        if args.command == "migrate":
            audited = _read_migration_audit(_path(dsn))
            print(
                json.dumps(
                    {
                        "migratable_rows": len(candidates),
                        "audited_migrations": len(audited),
                        "target_schema": SCHEMA_VERSION,
                    },
                    ensure_ascii=False,
                )
            )
            if not args.apply:
                return 0
            if candidates:
                _apply_migrations(_path(dsn), candidates)
            audited = _read_migration_audit(_path(dsn))
            backend = args.event_store_backend or os.environ.get(
                "SHIJIAJING_EVENT_STORE_BACKEND", "disabled"
            )
            event_dsn = args.event_store_dsn or os.environ.get("SHIJIAJING_EVENT_STORE_DSN")
            events, skipped = _migration_events(audited)
            if events and backend != "disabled":
                if not event_dsn:
                    raise ValueError(
                        "未配置 SHIJIAJING_EVENT_STORE_DSN，无法追加 checkpoint_migrated"
                    )
                run_async(_append_migration_events(backend, event_dsn, events))
            print(
                json.dumps(
                    {
                        "applied_rows": len(candidates),
                        "checkpoint_migrated_events": len(events) if backend != "disabled" else 0,
                        "audit_skipped_missing_ids": skipped,
                    },
                    ensure_ascii=False,
                )
            )
        return 0
    except Exception as exc:
        print(
            "迁移检查失败："
            + public_error_message(exc, fallback="迁移检查失败，请检查配置和状态存储"),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
