"""用户修正示例：识别后用户纠正品牌/型号，第二轮不重复调用 VLM（§25）。

用法：
    python examples/correction_example.py --image path/to/photo.jpg --brand Sony --model WH-1000XM5

第一轮用图片识别，第二轮携带 RecognitionCorrection（必须作用于当前会话最新的
recognition_id，见 §6.3）。修正后 Agent 直接以修正值继续检索，不再次调用 VLM。
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from shijiajing_agent.contracts import AgentRequest, RecognitionCorrection

if __package__:
    from ._common import build_image_ref, load_settings_or_exit, print_response, run_session
else:  # 以脚本方式运行（python examples/correction_example.py）
    from _common import build_image_ref, load_settings_or_exit, print_response, run_session


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="用户修正示例")
    parser.add_argument("--image", required=True, help="本地图片路径（jpg/jpeg/png/webp）")
    parser.add_argument("--brand", default=None, help="修正品牌（留空表示不修正）")
    parser.add_argument("--model", default=None, help="修正型号")
    parser.add_argument("--category-id", dest="category_id", default=None, help="修正品类 ID")
    args = parser.parse_args(argv)

    if not any((args.brand, args.model, args.category_id)):
        print("请至少提供一个修正字段：--brand / --model / --category-id", file=sys.stderr)
        return 2

    image = build_image_ref(args.image)
    settings = load_settings_or_exit()
    first = AgentRequest(
        session_id="example-correction-session",
        request_id="example-correction-0",
        image=image,
        text="看看这个商品的价格",
    )

    async def _run() -> None:
        first_response = (await run_session([first], settings=settings))[0]
        print_response(first_response, 1)
        if first_response.recognition is None:
            print("\n第一轮未产出识别结果，无法进行修正。", file=sys.stderr)
            return
        # 修正必须作用于当前会话最新的 recognition_id（§6.3）
        second = AgentRequest(
            session_id="example-correction-session",
            request_id="example-correction-1",
            correction=RecognitionCorrection(
                recognition_id=first_response.recognition.recognition_id,
                brand=args.brand,
                model=args.model,
                category_id=args.category_id,
            ),
        )
        second_response = (await run_session([second], settings=settings))[0]
        print_response(second_response, 2)

    asyncio.run(_run())
    return 0


if __name__ == "__main__":
    sys.exit(main())
