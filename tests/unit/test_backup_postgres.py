"""PostgreSQL dump/restore CLI 的安全命令契约测试。"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from shijiajing_agent.tools import backup_postgres


def test_backup_rejects_existing_dump_without_apply(tmp_path: Path, monkeypatch) -> None:
    dump = tmp_path / "backup.dump"
    dump.write_bytes(b"existing")
    calls: list[list[str]] = []
    monkeypatch.setattr(
        backup_postgres.subprocess, "run", lambda *args, **kwargs: calls.append(args[0])
    )

    assert (
        backup_postgres.main(
            ["backup", "--source-dsn", "postgresql://user:secret@localhost/db", "--dump", str(dump)]
        )
        == 2
    )
    assert calls == []


def test_backup_runs_dump_and_archive_verification(tmp_path: Path, monkeypatch, capsys) -> None:
    dump = tmp_path / "backup.dump"
    calls: list[list[str]] = []
    environments: list[dict[str, str] | None] = []

    def fake_run(command, *, check, capture_output, text, **kwargs):
        calls.append(command)
        environments.append(kwargs.get("env"))
        if Path(command[0]).name == "pg_dump":
            file_index = command.index("--file") + 1
            Path(command[file_index]).write_bytes(b"custom-format-dump")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(backup_postgres.shutil, "which", lambda name: name)
    monkeypatch.setattr(backup_postgres.subprocess, "run", fake_run)

    assert (
        backup_postgres.main(
            [
                "backup",
                "--source-dsn",
                "postgresql://user:secret@localhost/db",
                "--dump",
                str(dump),
            ]
        )
        == 0
    )
    assert [Path(command[0]).name for command in calls] == ["pg_dump", "pg_restore"]
    assert calls[0][1] == "--format=custom"
    assert calls[0][2] == "--file"
    assert Path(calls[0][3]).parent == dump.parent
    assert Path(calls[0][3]).name.startswith(f".{dump.name}.")
    assert Path(calls[0][3]).suffix == ".tmp"
    assert calls[0][4] == "--dbname"
    assert "secret" not in calls[0][5]
    assert "PGPASSWORD" not in calls[0][5]
    assert environments[0] is not None
    assert environments[0]["PGPASSWORD"] == "secret"
    assert dump.exists()
    assert json.loads(capsys.readouterr().out)["archive_verified"] is True


def test_backup_verification_failure_preserves_existing_dump_and_cleans_staging(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    dump = tmp_path / "backup.dump"
    dump.write_bytes(b"existing-dump")
    dsn = "postgresql://user:secret@localhost/db"

    def fake_run(command, *, check, capture_output, text, **kwargs):
        if Path(command[0]).name == "pg_dump":
            file_index = command.index("--file") + 1
            Path(command[file_index]).write_bytes(b"new-dump")
            return subprocess.CompletedProcess(command, 0, "", "")
        raise subprocess.CalledProcessError(
            1, command, stderr="archive verification failed", output=""
        )

    monkeypatch.setattr(backup_postgres.shutil, "which", lambda name: name)
    monkeypatch.setattr(backup_postgres.subprocess, "run", fake_run)

    assert (
        backup_postgres.main(["backup", "--source-dsn", dsn, "--dump", str(dump), "--apply"]) == 2
    )
    assert dump.read_bytes() == b"existing-dump"
    assert not list(tmp_path.glob(f".{dump.name}.*.tmp"))
    assert "archive verification failed" in capsys.readouterr().err


def test_restore_requires_apply_and_verifies_before_write(tmp_path: Path, monkeypatch) -> None:
    dump = tmp_path / "backup.dump"
    dump.write_bytes(b"custom-format-dump")
    calls: list[list[str]] = []
    environments: list[dict[str, str] | None] = []

    def fake_run(command, *, check, capture_output, text, **kwargs):
        calls.append(command)
        environments.append(kwargs.get("env"))
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(backup_postgres.shutil, "which", lambda name: name)
    monkeypatch.setattr(backup_postgres.subprocess, "run", fake_run)

    assert (
        backup_postgres.main(
            [
                "restore",
                "--dump",
                str(dump),
                "--target-dsn",
                "postgresql://user:secret@localhost/isolated",
            ]
        )
        == 2
    )
    assert calls == []

    assert (
        backup_postgres.main(
            [
                "restore",
                "--dump",
                str(dump),
                "--target-dsn",
                "postgresql://user:secret@localhost/isolated",
                "--apply",
            ]
        )
        == 0
    )
    assert [Path(command[0]).name for command in calls] == ["pg_restore", "pg_restore"]
    assert calls[0][1] == "--list"
    assert calls[1][1] == "--exit-on-error"
    assert calls[1][2] == "--dbname"
    assert "secret" not in calls[1][3]
    assert environments[1] is not None
    assert environments[1]["PGPASSWORD"] == "secret"


def test_verify_reports_missing_pg_restore(tmp_path: Path, monkeypatch, capsys) -> None:
    dump = tmp_path / "backup.dump"
    dump.write_bytes(b"custom-format-dump")
    monkeypatch.setattr(backup_postgres.shutil, "which", lambda name: None)

    assert backup_postgres.main(["verify", "--dump", str(dump)]) == 2
    assert "pg_restore" in capsys.readouterr().err


def test_backup_redacts_dsn_from_tool_errors(tmp_path: Path, monkeypatch, capsys) -> None:
    dump = tmp_path / "backup.dump"
    dsn = "postgresql://user:secret@localhost/db"

    def fake_run(command, *, check, capture_output, text, **kwargs):
        raise subprocess.CalledProcessError(
            1, command, stderr=f"connection failed for {dsn}", output=""
        )

    monkeypatch.setattr(backup_postgres.shutil, "which", lambda name: name)
    monkeypatch.setattr(backup_postgres.subprocess, "run", fake_run)

    assert backup_postgres.main(["backup", "--source-dsn", dsn, "--dump", str(dump)]) == 2
    error = capsys.readouterr().err
    assert dsn not in error
    assert "<redacted>" in error


def test_backup_rejects_sslpassword_without_exposing_dsn(tmp_path: Path, capsys) -> None:
    dsn = "postgresql://user:secret@localhost/db?sslpassword=private-key-secret"

    assert backup_postgres.main(["backup", "--source-dsn", dsn, "--dump", str(tmp_path / "x")]) == 2

    error = capsys.readouterr().err
    assert dsn not in error
    assert "private-key-secret" not in error
    assert "sslpassword" in error
