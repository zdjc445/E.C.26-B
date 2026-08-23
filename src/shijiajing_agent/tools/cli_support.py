"""运维 CLI 的公开错误边界。"""

from __future__ import annotations

import sys

from shijiajing_agent.errors import ShijiajingError

_SAFE_CONFIGURATION_PREFIXES = (
    "配置错误：",
    "缺少必要配置：",
    "二期配置错误：",
    "--verify-trace 要求",
)


def configure_utf8_output() -> None:
    """让支持 reconfigure 的 stdout/stderr 以 UTF-8 输出。"""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def public_error_message(exc: Exception, *, fallback: str) -> str:
    """保留可操作配置错误，隐藏 provider、主机、DSN 和密钥原文。"""
    if isinstance(exc, ShijiajingError):
        return exc.user_message
    message = str(exc)
    if message.startswith(_SAFE_CONFIGURATION_PREFIXES):
        return message
    return fallback
