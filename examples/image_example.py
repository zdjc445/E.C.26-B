"""图片示例：VLM 商品识别 + 比价（可加补充文本）。

用法：
    python examples/image_example.py --image path/to/photo.jpg
    python examples/image_example.py --image path/to/photo.jpg --text "预算2000以内"

需要 SHIJIAJING_* 外部配置；图片通过 data URL 内联引用，不经过对象存储。
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from shijiajing_agent.contracts import AgentRequest

if __package__:
    from ._common import build_image_ref, load_settings_or_exit, print_response, run_session
else:  # 以脚本方式运行（python examples/image_example.py）
    from _common import build_image_ref, load_settings_or_exit, print_response, run_session


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="图片比价示例")
    parser.add_argument("--image", required=True, help="本地图片路径（jpg/jpeg/png/webp）")
    parser.add_argument("--text", default=None, help="可选补充文本（如预算、偏好）")
    args = parser.parse_args(argv)

    image = build_image_ref(args.image)
    settings = load_settings_or_exit()
    request = AgentRequest(
        session_id="example-image-session",
        request_id="example-image-0",
        text=args.text,
        image=image,
    )
    responses = asyncio.run(run_session([request], settings=settings))
    print_response(responses[0])
    return 0


if __name__ == "__main__":
    sys.exit(main())
