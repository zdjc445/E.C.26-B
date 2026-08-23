"""示例共享逻辑：配置校验、图片引用、会话执行和终端展示。"""

from __future__ import annotations

import base64
import hashlib
import sys
from pathlib import Path

from shijiajing_agent.asyncio_compat import run as run_async
from shijiajing_agent.config import Settings, load_settings
from shijiajing_agent.contracts import (
    AgentRequest,
    AgentResponse,
    ImageContentType,
    ImageRef,
    RecognitionCorrection,
)
from shijiajing_agent.deps import make_deps
from shijiajing_agent.runtime import open_agent_runtime


def load_settings_or_exit() -> Settings:
    """读取真实配置；缺失项按精确 SHIJIAJING_* 名称退出 2。"""
    try:
        settings = load_settings()
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2) from exc
    missing = settings.validate(require_real_adapters=True)
    if missing:
        names = ", ".join(f"SHIJIAJING_{name}" for name in missing)
        print(f"缺少必要配置：{names}", file=sys.stderr)
        raise SystemExit(2)
    engineering_errors = settings.validate_engineering()
    if engineering_errors:
        print("二期配置错误：" + ", ".join(engineering_errors), file=sys.stderr)
        raise SystemExit(2)
    return settings


def build_image_ref(path: str) -> ImageRef:
    """把本地 JPEG/PNG/WebP 转为受控 data URL 引用。"""
    image_path = Path(path)
    content_types = {
        ".jpg": ImageContentType.JPEG,
        ".jpeg": ImageContentType.JPEG,
        ".png": ImageContentType.PNG,
        ".webp": ImageContentType.WEBP,
    }
    content_type = content_types.get(image_path.suffix.lower())
    if content_type is None:
        print("图片格式只支持 .jpg/.jpeg/.png/.webp", file=sys.stderr)
        raise SystemExit(2)
    try:
        data = image_path.read_bytes()
    except OSError as exc:
        print(f"图片读取失败：{image_path}：{exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    digest = hashlib.sha256(data).hexdigest()
    encoded = base64.b64encode(data).decode("ascii")
    return ImageRef(
        image_id=f"img:{digest[:16]}",
        uri=f"data:{content_type.value};base64,{encoded}",
        content_type=content_type,
        sha256=digest,
    )


async def _run_with_facade(
    requests: list[AgentRequest], *, settings: Settings
) -> list[AgentResponse]:
    async with open_agent_runtime(settings, deps_factory=make_deps) as facade:
        return [await facade.run(request) for request in requests]


async def run_session(
    requests: list[AgentRequest], *, settings: Settings | None = None
) -> list[AgentResponse]:
    """在同一 Facade 中按顺序执行多轮请求。显式 Settings 供 Fake 测试注入。"""
    effective_settings = settings if settings is not None else load_settings_or_exit()
    return await _run_with_facade(requests, settings=effective_settings)


async def run_correction_session(
    *,
    image: ImageRef,
    brand: str | None,
    model: str | None,
    settings: Settings,
) -> list[AgentResponse]:
    """先识别，再在同一 Facade 内提交一次用户修正。"""
    async with open_agent_runtime(settings, deps_factory=make_deps) as facade:
        first = await facade.run(
            AgentRequest(
                session_id="correction-example",
                request_id="r1",
                image=image,
            )
        )
        if first.recognition is None:
            return [first]
        second = await facade.run(
            AgentRequest(
                session_id="correction-example",
                request_id="r2",
                correction=RecognitionCorrection(
                    recognition_id=first.recognition.recognition_id,
                    brand=brand,
                    model=model,
                ),
            )
        )
        return [first, second]


def print_response(response: AgentResponse, *, index: int) -> None:
    print(f"第 {index} 轮")
    print(f"状态：{response.status.value}")
    if response.recognition is not None:
        recognition = response.recognition
        print(
            "识别："
            + " ".join(
                item
                for item in (
                    recognition.category_name,
                    recognition.brand,
                    recognition.model,
                )
                if item
            )
        )
    for ranked in response.groups:
        group = ranked.group
        price = "暂无"
        if group.min_price is not None:
            price = f"{group.min_price:g} 元"
        print(f"比价组 {ranked.rank}：最低 {price}，{group.offer_count} 个报价")
    if response.clarification is not None:
        print(f"需要补充：{response.clarification.question}")
    if response.message:
        print(response.message)
    for notice in response.notices:
        print(f"提示：{notice}")


def run_and_print(requests: list[AgentRequest], *, settings: Settings) -> int:
    responses = run_async(run_session(requests, settings=settings))
    for index, response in enumerate(responses, start=1):
        print_response(response, index=index)
    return 0


def parse_optional_text(value: str | None) -> str | None:
    return value.strip() if value and value.strip() else None
