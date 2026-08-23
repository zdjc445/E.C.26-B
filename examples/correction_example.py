"""图片识别后提交品牌/型号修正的示例。"""

from __future__ import annotations

import argparse
import sys

from examples._common import (
    build_image_ref,
    load_settings_or_exit,
    print_response,
    run_correction_session,
)
from shijiajing_agent.asyncio_compat import run as run_async
from shijiajing_agent.config import Settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="识价镜用户修正示例")
    parser.add_argument("--image", required=True)
    parser.add_argument("--brand")
    parser.add_argument("--model")
    args = parser.parse_args(argv)
    if not args.brand and not args.model:
        print("至少提供 --brand 或 --model", file=sys.stderr)
        return 2
    settings: Settings = load_settings_or_exit()
    responses = run_async(
        run_correction_session(
            image=build_image_ref(args.image),
            brand=args.brand,
            model=args.model,
            settings=settings,
        )
    )
    for index, response in enumerate(responses, start=1):
        print_response(response, index=index)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
