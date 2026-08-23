"""legacy checkpoint 显式迁移 CLI 的安全边界测试。"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from shijiajing_agent.tools.migrate_state import main


def _create_legacy_checkpoint(path: Path, *, identifiers: bool) -> None:
    payload: dict[str, object] = {"schema_version": "1.0"}
    if identifiers:
        payload.update(
            {
                "request_id": "request-1",
                "turn_id": "turn-1",
                "trace_id": "trace-1",
            }
        )
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE agent_checkpoint ("
            "session_id TEXT PRIMARY KEY, state_json TEXT NOT NULL, "
            "state_version INTEGER NOT NULL, schema_version TEXT NOT NULL, "
            "saved_at TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT INTO agent_checkpoint "
            "(session_id, state_json, state_version, schema_version, saved_at) "
            "VALUES (?, ?, ?, ?, ?)",
            ("session-1", json.dumps(payload), 7, "1.0", "2026-08-22T00:00:00+00:00"),
        )


def _checkpoint_schema(path: Path) -> str:
    with sqlite3.connect(path) as conn:
        return str(conn.execute("SELECT schema_version FROM agent_checkpoint").fetchone()[0])


def test_migrate_state_dry_run_does_not_write(tmp_path: Path) -> None:
    checkpoint = tmp_path / "checkpoint.db"
    _create_legacy_checkpoint(checkpoint, identifiers=True)

    assert main(["migrate", "--dsn", str(checkpoint)]) == 0
    assert _checkpoint_schema(checkpoint) == "1.0"


def test_migrate_state_apply_commits_before_audit(tmp_path: Path) -> None:
    checkpoint = tmp_path / "checkpoint.db"
    event_store = tmp_path / "events.db"
    _create_legacy_checkpoint(checkpoint, identifiers=True)

    assert (
        main(
            [
                "migrate",
                "--dsn",
                str(checkpoint),
                "--apply",
                "--event-store-backend",
                "sqlite",
                "--event-store-dsn",
                str(event_store),
            ]
        )
        == 0
    )
    assert _checkpoint_schema(checkpoint) == "1.1"
    with sqlite3.connect(event_store) as conn:
        row = conn.execute("SELECT event_type, payload_json FROM agent_event").fetchone()
    assert row is not None
    assert row[0] == "checkpoint_migrated"
    assert json.loads(row[1]) == {"from_schema": "1.0", "to_schema": "1.1"}


def test_migrate_state_never_fabricates_audit_identifiers(tmp_path: Path) -> None:
    checkpoint = tmp_path / "checkpoint.db"
    event_store = tmp_path / "events.db"
    _create_legacy_checkpoint(checkpoint, identifiers=False)

    assert (
        main(
            [
                "migrate",
                "--dsn",
                str(checkpoint),
                "--apply",
                "--event-store-backend",
                "sqlite",
                "--event-store-dsn",
                str(event_store),
            ]
        )
        == 0
    )
    assert _checkpoint_schema(checkpoint) == "1.1"
    assert not event_store.exists()


def test_migrate_state_retries_audit_after_event_store_failure(tmp_path: Path) -> None:
    checkpoint = tmp_path / "checkpoint.db"
    good_event_store = tmp_path / "events.db"
    _create_legacy_checkpoint(checkpoint, identifiers=True)

    assert (
        main(
            [
                "migrate",
                "--dsn",
                str(checkpoint),
                "--apply",
                "--event-store-backend",
                "sqlite",
                "--event-store-dsn",
                str(tmp_path / "missing" / "events.db"),
            ]
        )
        == 2
    )
    assert _checkpoint_schema(checkpoint) == "1.1"
    with sqlite3.connect(checkpoint) as conn:
        assert conn.execute("SELECT COUNT(*) FROM checkpoint_migration_audit").fetchone()[0] == 1

    assert (
        main(
            [
                "migrate",
                "--dsn",
                str(checkpoint),
                "--apply",
                "--event-store-backend",
                "sqlite",
                "--event-store-dsn",
                str(good_event_store),
            ]
        )
        == 0
    )
    with sqlite3.connect(good_event_store) as conn:
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM agent_event WHERE event_type = 'checkpoint_migrated'"
            ).fetchone()[0]
            == 1
        )
