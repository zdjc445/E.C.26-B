"""文本多轮比价示例。"""

from __future__ import annotations

import argparse

from examples._common import load_settings_or_exit, run_and_print
from shijiajing_agent.config import Settings
from shijiajing_agent.contracts import AgentRequest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="识价镜文本比价示例")
    parser.add_argument("texts", nargs="+", help="按顺序输入一轮或多轮文本")
    args = parser.parse_args(argv)
    settings: Settings = load_settings_or_exit()
    requests = [
        AgentRequest(session_id="text-example", request_id=f"r{index}", text=text)
        for index, text in enumerate(args.texts, start=1)
    ]
    return run_and_print(requests, settings=settings)


if __name__ == "__main__":
    raise SystemExit(main())
