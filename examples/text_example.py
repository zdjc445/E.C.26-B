"""文本示例：一轮文本比价查询（可加第二轮追问）。

用法：
    python examples/text_example.py "索尼耳机 预算2000以内"
    python examples/text_example.py "索尼耳机 预算2000以内" "只要黑色款"

需要 SHIJIAJING_* 外部配置；缺失时打印精确缺失项（见 README.md）。
"""

from __future__ import annotations

import asyncio
import sys

from shijiajing_agent.contracts import AgentRequest

if __package__:
    from ._common import load_settings_or_exit, print_response, run_session
else:  # 以脚本方式运行（python examples/text_example.py）
    from _common import load_settings_or_exit, print_response, run_session


def main(argv: list[str] | None = None) -> int:
    args = list(argv) if argv is not None else sys.argv[1:]
    if not args:
        args = ["索尼耳机 预算2000以内"]
    texts = args[:2]
    settings = load_settings_or_exit()
    requests = [
        AgentRequest(
            session_id="example-text-session",
            request_id=f"example-text-{i}",
            text=text,
        )
        for i, text in enumerate(texts)
    ]
    responses = asyncio.run(run_session(requests, settings=settings))
    for index, response in enumerate(responses, start=1):
        print_response(response, index)
    return 0


if __name__ == "__main__":
    sys.exit(main())
