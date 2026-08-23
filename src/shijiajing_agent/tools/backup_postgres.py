"""PostgreSQL dump/restore 的显式安全封装。"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from shijiajing_agent.tools.cli_support import configure_utf8_output


def _args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="shijiajing-backup-postgres")
    sub = parser.add_subparsers(dest="mode", required=True)

    backup = sub.add_parser("backup", help="生成 custom-format PostgreSQL dump")
    backup.add_argument("--source-dsn", required=True)
    backup.add_argument("--dump", type=Path, required=True)
    backup.add_argument("--apply", action="store_true", help="允许覆盖已有 dump 文件")

    verify = sub.add_parser("verify", help="验证 custom-format dump 可被 pg_restore 读取")
    verify.add_argument("--dump", type=Path, required=True)

    restore = sub.add_parser("restore", help="把 dump 恢复到指定 PostgreSQL 数据库")
    restore.add_argument("--dump", type=Path, required=True)
    restore.add_argument("--target-dsn", required=True)
    restore.add_argument("--apply", action="store_true", help="确认执行恢复写入")
    return parser.parse_args(argv)


def _require_tool(name: str) -> str:
    executable = shutil.which(name)
    if executable is None:
        raise ValueError(f"未找到 PostgreSQL 工具：{name}；请安装 PostgreSQL client tools")
    return executable


def _run(
    command: list[str],
    *,
    sensitive_values: tuple[str, ...] = (),
    env: Mapping[str, str] | None = None,
) -> None:
    try:
        if env is None:
            subprocess.run(command, check=True, capture_output=True, text=True)
        else:
            subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
                env=dict(env),
            )
    except FileNotFoundError as exc:
        raise ValueError(f"未找到 PostgreSQL 工具：{command[0]}") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        for value in sensitive_values:
            if value:
                detail = detail.replace(value, "<redacted>")
        message = f"{Path(command[0]).name} 执行失败（退出码 {exc.returncode}）"
        if detail:
            message += f": {detail}"
        raise ValueError(message) from exc


def _safe_connection_target(dsn: str) -> tuple[str, Mapping[str, str] | None, tuple[str, ...]]:
    """把密码从 client-tool 命令行移到子进程环境。

    ``pg_dump`` 和 ``pg_restore`` 都支持 libpq connection string。先由 psycopg
    按 libpq 规则解析，再重新生成不含密码的 connection string，避免自行猜测
    URI 或 keyword/value DSN 的格式。密码只进入子进程的 ``PGPASSWORD`` 环境变量。
    """
    if not dsn:
        raise ValueError("PostgreSQL DSN 不能为空")
    try:
        from psycopg import conninfo
    except ImportError as exc:
        raise ValueError(
            "安全解析 PostgreSQL DSN 需要 psycopg；请安装 shijiajing-agent[postgres]"
        ) from exc
    try:
        values = conninfo.conninfo_to_dict(dsn)
    except Exception as exc:
        raise ValueError("PostgreSQL DSN 格式无效") from exc
    password = values.pop("password", None)
    if values.get("sslpassword") not in (None, ""):
        raise ValueError("PostgreSQL DSN 的 sslpassword 不支持通过命令行备份")
    try:
        safe_dsn = conninfo.make_conninfo(**cast(dict[str, str], values))
    except Exception as exc:
        raise ValueError("PostgreSQL DSN 格式无效") from exc

    child_env: Mapping[str, str] | None = None
    if password is not None:
        password_text = str(password)
        child_env_dict = os.environ.copy()
        child_env_dict["PGPASSWORD"] = password_text
        child_env = child_env_dict
    else:
        password_text = None
    sensitive_values = tuple(value for value in (dsn, password_text) if value)
    return safe_dsn, child_env, sensitive_values


def _require_dump(path: Path) -> Path:
    resolved = path.resolve()
    if not resolved.is_file():
        raise ValueError(f"PostgreSQL dump 文件不存在：{resolved}")
    if resolved.stat().st_size == 0:
        raise ValueError(f"PostgreSQL dump 文件为空：{resolved}")
    return resolved


def _verify_dump(path: Path) -> None:
    pg_restore = _require_tool("pg_restore")
    _run([pg_restore, "--list", str(path)])


def _backup(args: argparse.Namespace) -> dict[str, object]:
    dump = args.dump.resolve()
    if dump.exists() and not args.apply:
        raise ValueError(f"dump 文件已存在，覆盖前必须显式指定 --apply：{dump}")
    safe_dsn, child_env, sensitive_values = _safe_connection_target(args.source_dsn)
    pg_dump = _require_tool("pg_dump")
    dump.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="wb", prefix=f".{dump.name}.", suffix=".tmp", dir=dump.parent, delete=False
    ) as temporary_file:
        temporary_dump = Path(temporary_file.name)
    try:
        _run(
            [
                pg_dump,
                "--format=custom",
                "--file",
                str(temporary_dump),
                "--dbname",
                safe_dsn,
            ],
            sensitive_values=sensitive_values,
            env=child_env,
        )
        _verify_dump(_require_dump(temporary_dump))
        temporary_dump.replace(dump)
    finally:
        temporary_dump.unlink(missing_ok=True)
    return {"mode": "backup", "dump": str(dump), "archive_verified": True}


def _restore(args: argparse.Namespace) -> dict[str, object]:
    if not args.apply:
        raise ValueError("restore 必须显式指定 --apply")
    dump = _require_dump(args.dump)
    safe_dsn, child_env, sensitive_values = _safe_connection_target(args.target_dsn)
    pg_restore = _require_tool("pg_restore")
    _verify_dump(dump)
    _run(
        [pg_restore, "--exit-on-error", "--dbname", safe_dsn, str(dump)],
        sensitive_values=sensitive_values,
        env=child_env,
    )
    return {"mode": "restore", "dump": str(dump), "restored": True}


def main(argv: list[str] | None = None) -> int:
    configure_utf8_output()
    args = _args(argv)
    try:
        if args.mode == "backup":
            result = _backup(args)
        elif args.mode == "restore":
            result = _restore(args)
        else:
            dump = _require_dump(args.dump)
            _verify_dump(dump)
            result = {"mode": "verify", "dump": str(dump), "archive_verified": True}
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except Exception as exc:
        print(f"PostgreSQL backup 操作失败：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
