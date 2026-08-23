"""测试运行时公共设置。"""

from __future__ import annotations

import asyncio
import selectors
import sys
from collections.abc import Callable, Mapping

import pytest


@pytest.hookimpl(optionalhook=True)
def pytest_asyncio_loop_factories(
    config: object, item: object
) -> Mapping[str, Callable[[], asyncio.AbstractEventLoop]]:
    """为 pytest-asyncio 1.4+ 提供 Windows 的 SelectorEventLoop 工厂。"""

    del config, item
    if sys.platform == "win32":
        return {"selector": lambda: asyncio.SelectorEventLoop(selectors.SelectSelector())}
    return {"default": asyncio.new_event_loop}
