"""SQLite backup API 的复制、恢复和完整性校验测试。"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

from shijiajing_agent.tools import backup_sqlite
from shijiajing_agent.tools.backup_sqlite import main


def _create_db(path: Path, value: str) -> None:
    with closing(sqlite3.connect(path)) as conn:
        conn.execute("CREATE TABLE item (value TEXT NOT NULL)")
        conn.execute("INSERT INTO item (value) VALUES (?)", (value,))
        conn.commit()


def _value(path: Path) -> str:
    with sqlite3.connect(path) as conn:
        return str(conn.execute("SELECT value FROM item").fetchone()[0])


def test_sqlite_backup_and_restore_use_backup_api(tmp_path: Path) -> None:
    source = tmp_path / "source.db"
    backup = tmp_path / "backup" / "source.db"
    restored = tmp_path / "restored.db"
    _create_db(source, "before")

    assert (
        main(
            [
                "--mode",
                "backup",
                "--source-dsn",
                str(source),
                "--target-dsn",
                str(backup),
            ]
        )
        == 0
    )
    assert _value(backup) == "before"

    assert (
        main(
            [
                "--mode",
                "restore",
                "--source-dsn",
                str(backup),
                "--target-dsn",
                str(restored),
            ]
        )
        == 2
    )
    assert (
        main(
            [
                "--mode",
                "restore",
                "--source-dsn",
                str(backup),
                "--target-dsn",
                str(restored),
                "--apply",
            ]
        )
        == 0
    )
    assert _value(restored) == "before"


def test_sqlite_verify_compares_integrity_and_content_digest(tmp_path: Path, capsys) -> None:
    source = tmp_path / "source.db"
    target = tmp_path / "verify" / "source.db"
    _create_db(source, "before")

    assert (
        main(
            [
                "--mode",
                "verify",
                "--source-dsn",
                str(source),
                "--target-dsn",
                str(target),
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert result["source_integrity_check"] == "ok"
    assert result["target_integrity_check"] == "ok"
    assert result["content_equal"] is True
    assert result["source_digest"] == result["target_digest"]


def test_sqlite_backup_rejects_existing_target_without_apply(tmp_path: Path, capsys) -> None:
    source = tmp_path / "source.db"
    target = tmp_path / "target.db"
    _create_db(source, "source")
    _create_db(target, "existing")

    assert (
        main(
            [
                "--mode",
                "backup",
                "--source-dsn",
                str(source),
                "--target-dsn",
                str(target),
            ]
        )
        == 2
    )
    assert "必须显式指定 --apply" in capsys.readouterr().err
    assert _value(target) == "existing"


def test_sqlite_restore_rejects_overwriting_existing_target_without_apply(
    tmp_path: Path, capsys
) -> None:
    source = tmp_path / "source.db"
    backup = tmp_path / "backup.db"
    target = tmp_path / "target.db"
    _create_db(source, "source")
    _create_db(backup, "backup")
    _create_db(target, "existing")

    assert (
        main(
            [
                "--mode",
                "restore",
                "--source-dsn",
                str(backup),
                "--target-dsn",
                str(target),
            ]
        )
        == 2
    )
    assert "必须显式指定 --apply" in capsys.readouterr().err
    assert _value(target) == "existing"


def test_sqlite_verify_rejects_existing_target_without_apply(tmp_path: Path, capsys) -> None:
    source = tmp_path / "source.db"
    target = tmp_path / "target.db"
    _create_db(source, "source")
    _create_db(target, "existing")

    assert (
        main(
            [
                "--mode",
                "verify",
                "--source-dsn",
                str(source),
                "--target-dsn",
                str(target),
            ]
        )
        == 2
    )
    assert "必须显式指定 --apply" in capsys.readouterr().err
    assert _value(target) == "existing"


def test_sqlite_backup_allows_existing_target_with_apply(tmp_path: Path) -> None:
    source = tmp_path / "source.db"
    target = tmp_path / "target.db"
    _create_db(source, "source")
    _create_db(target, "existing")

    assert (
        main(
            [
                "--mode",
                "backup",
                "--source-dsn",
                str(source),
                "--target-dsn",
                str(target),
                "--apply",
            ]
        )
        == 0
    )
    assert _value(target) == "source"


def test_sqlite_failure_keeps_existing_target_and_cleans_staging(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    source = tmp_path / "source.db"
    target = tmp_path / "target.db"
    _create_db(source, "source")
    _create_db(target, "existing")
    original_integrity_check = backup_sqlite._integrity_check

    def fail_staging(path: Path) -> str:
        if path.name.startswith(f".{target.name}."):
            raise ValueError("simulated staging integrity failure")
        return original_integrity_check(path)

    monkeypatch.setattr(backup_sqlite, "_integrity_check", fail_staging)

    assert (
        main(
            [
                "--mode",
                "backup",
                "--source-dsn",
                str(source),
                "--target-dsn",
                str(target),
                "--apply",
            ]
        )
        == 2
    )
    assert "simulated staging integrity failure" in capsys.readouterr().err
    assert _value(target) == "existing"
    assert not list(tmp_path.glob(f".{target.name}.*.tmp"))
