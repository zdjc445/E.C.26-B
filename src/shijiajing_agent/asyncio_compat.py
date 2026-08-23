"""跨平台异步运行时兼容层。"""

from __future__ import annotations

import asyncio
import selectors
import sys
from collections.abc import Coroutine
from typing import Any


def run[ResultT](coro: Coroutine[Any, Any, ResultT]) -> ResultT:
    """运行协程；Windows 使用 psycopg 兼容的 SelectorEventLoop。"""

    if sys.platform == "win32":
        return asyncio.run(
            coro,
            loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()),
        )
    return asyncio.run(coro)
