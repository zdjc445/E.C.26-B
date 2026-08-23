"""使用 SQLite backup API 复制或恢复单个 SQLite 数据库。"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
import tempfile
from contextlib import closing
from pathlib import Path

from shijiajing_agent.tools.cli_support import configure_utf8_output


def _sqlite_path(dsn: str) -> Path:
    for prefix in ("sqlite:///", "sqlite://"):
        if dsn.startswith(prefix):
            dsn = dsn[len(prefix) :]
            break
    if not dsn:
        raise ValueError("SQLite DSN 不能为空")
    return Path(dsn).resolve()


def _backup(source: Path, target: Path) -> dict[str, object]:
    target.parent.mkdir(parents=True, exist_ok=True)
    source_integrity = _integrity_check(source)
    with tempfile.NamedTemporaryFile(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent, delete=False
    ) as temporary_file:
        staging = Path(temporary_file.name)
    try:
        with (
            closing(sqlite3.connect(source)) as source_conn,
            closing(sqlite3.connect(staging)) as target_conn,
        ):
            source_conn.backup(target_conn)
            target_conn.commit()
        target_integrity = _integrity_check(staging)
        source_digest = _database_digest(source)
        target_digest = _database_digest(staging)
        if source_digest != target_digest:
            raise ValueError("备份后 SQLite 内容摘要不一致")
        staging.replace(target)
        return {
            "integrity_check": target_integrity,
            "source_integrity_check": source_integrity,
            "target_integrity_check": target_integrity,
            "source_digest": source_digest,
            "target_digest": target_digest,
            "content_equal": True,
        }
    finally:
        staging.unlink(missing_ok=True)


def _integrity_check(path: Path) -> str:
    with closing(sqlite3.connect(path)) as conn:
        result = conn.execute("PRAGMA integrity_check").fetchone()
    if result is None or result[0] != "ok":
        raise ValueError(f"SQLite integrity_check 失败: {path}: {result[0] if result else None}")
    return "ok"


def _database_digest(path: Path) -> str:
    """计算 SQLite 可重放转储摘要，用于备份后隔离校验。"""
    with closing(sqlite3.connect(path)) as conn:
        dump = "\n".join(conn.iterdump()).encode("utf-8")
    return hashlib.sha256(dump).hexdigest()


def _args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="shijiajing-backup-sqlite")
    parser.add_argument("--mode", choices=("backup", "restore", "verify"), required=True)
    parser.add_argument("--source-dsn", required=True, help="源 SQLite DSN")
    parser.add_argument("--target-dsn", required=True, help="目标 SQLite DSN")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="允许 backup/restore/verify 覆盖已有目标文件",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    configure_utf8_output()
    args = _args(argv)
    try:
        source = _sqlite_path(args.source_dsn)
        target = _sqlite_path(args.target_dsn)
        if source == target:
            raise ValueError("source-dsn 与 target-dsn 不能指向同一文件")
        if not source.exists():
            raise ValueError(f"源 SQLite 文件不存在: {source}")
        if args.mode == "backup" and target.exists() and not args.apply:
            raise ValueError("backup 的目标文件已存在，覆盖前必须显式指定 --apply")
        if args.mode == "restore" and not args.apply:
            raise ValueError("restore 必须显式指定 --apply")
        if args.mode == "verify" and target.exists() and not args.apply:
            raise ValueError("verify 的目标文件已存在，覆盖前必须显式指定 --apply")
        result = _backup(source, target)
        print(
            json.dumps(
                {
                    "mode": args.mode,
                    "source": str(source),
                    "target": str(target),
                    **result,
                },
                ensure_ascii=False,
            )
        )
        return 0
    except Exception as exc:
        print(f"SQLite backup 操作失败：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
