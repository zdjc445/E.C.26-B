"""图片识别加文本比价示例。"""

from __future__ import annotations

import argparse

from examples._common import (
    build_image_ref,
    load_settings_or_exit,
    parse_optional_text,
    run_and_print,
)
from shijiajing_agent.config import Settings
from shijiajing_agent.contracts import AgentRequest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="识价镜图片比价示例")
    parser.add_argument("--image", required=True)
    parser.add_argument("--text")
    args = parser.parse_args(argv)
    settings: Settings = load_settings_or_exit()
    request = AgentRequest(
        session_id="image-example",
        request_id="r1",
        image=build_image_ref(args.image),
        text=parse_optional_text(args.text),
    )
    return run_and_print([request], settings=settings)


if __name__ == "__main__":
    raise SystemExit(main())
