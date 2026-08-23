"""跨平台异步 CLI 运行器测试。"""

from __future__ import annotations

from shijiajing_agent.asyncio_compat import run


async def _value() -> int:
    return 42


def test_run_returns_coroutine_result() -> None:
    assert run(_value()) == 42
