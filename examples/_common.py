"""示例共用逻辑：装配真实依赖、执行多轮请求、打印响应。

示例依赖真实外部配置（模型、检索、checkpoint），缺失时打印精确缺失项后退出。
测试可通过 ``deps`` 参数注入 Fake 端口（见 tests/unit/test_examples.py）。
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

from shijiajing_agent.config import Settings, load_settings
from shijiajing_agent.contracts import (
    AgentRequest,
    AgentResponse,
    ImageContentType,
    ImageRef,
)
from shijiajing_agent.deps import make_deps
from shijiajing_agent.facade import AgentDependencies, AgentFacade


def _reconfigure_console() -> None:
    """Windows 控制台默认 GBK，无法输出中文；统一按 UTF-8 打印（与 run_eval 一致）。"""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


_reconfigure_console()

_CONTENT_TYPES = {
    ".jpg": ImageContentType.JPEG,
    ".jpeg": ImageContentType.JPEG,
    ".png": ImageContentType.PNG,
    ".webp": ImageContentType.WEBP,
}


def load_settings_or_exit() -> Settings:
    """加载配置；外部资源缺失时打印精确缺失项并退出（§23）。"""
    settings = load_settings()
    missing = settings.validate(require_real_adapters=True)
    if missing:
        names = ", ".join(f"SHIJIAJING_{n}" for n in missing)
        print(f"缺少必要配置：{names}", file=sys.stderr)
        print("复制 .env.example 并补齐后，或设置对应环境变量后再运行。", file=sys.stderr)
        sys.exit(2)
    return settings


def build_image_ref(path: str) -> ImageRef:
    """本地图片 → ImageRef（data URL，不经过对象存储）。"""
    image_path = Path(path)
    if not image_path.exists():
        print(f"图片不存在：{image_path}", file=sys.stderr)
        sys.exit(2)
    ext = image_path.suffix.lower()
    content_type = _CONTENT_TYPES.get(ext)
    if content_type is None:
        print(f"不支持的图片格式：{ext}（支持 jpg/jpeg/png/webp）", file=sys.stderr)
        sys.exit(2)
    data = image_path.read_bytes()
    sha256 = hashlib.sha256(data).hexdigest()
    import base64

    uri = f"data:{content_type.value};base64,{base64.b64encode(data).decode('ascii')}"
    return ImageRef(
        image_id=f"example-{image_path.stem}",
        uri=uri,
        content_type=content_type,
        sha256=sha256,
    )


async def run_session(
    requests: list[AgentRequest],
    *,
    settings: Settings | None = None,
    deps: AgentDependencies | None = None,
) -> list[AgentResponse]:
    """按序执行多轮请求，返回每轮响应（同 session 串行恢复）。"""
    if deps is None:
        settings = settings or load_settings_or_exit()
        deps = make_deps(settings)
    facade = AgentFacade(deps)
    responses: list[AgentResponse] = []
    for request in requests:
        responses.append(await facade.run(request))
    return responses


def print_response(response: AgentResponse, index: int = 1) -> None:
    """打印一轮响应的可读摘要。"""
    print(f"\n===== 第 {index} 轮 =====")
    print(f"状态：{response.status.value}")
    if response.message:
        print(f"消息：{response.message}")
    rec = response.recognition
    if rec is not None:
        print(
            f"识别：{rec.category_name or rec.category_id or '未知品类'} "
            f"{rec.brand or ''} {rec.model or ''}"
            f"（置信度 {rec.overall_confidence:.2f}）"
        )
    if response.clarification is not None:
        c = response.clarification
        print(f"澄清：{c.question}")
        for option in c.options:
            print(f"  - {option.option_id}: {option.label}")
    for i, g in enumerate(response.groups, start=1):
        group = g.group
        price = f"¥{group.min_price:g}" if group.min_price is not None else "价格待确认"
        platforms = "、".join({o.platform for o in group.offers if o.platform}) or "未知"
        print(
            f"  第{i}名 [{group.sku_signature or group.group_id}] "
            f"{group.title or '未命名商品'}：最低 {price}（{platforms}，"
            f"{group.offer_count} 个报价）"
        )
    if response.notices:
        for notice in response.notices:
            print(f"提示：{notice}")
