"""示例脚本可运行性测试（§24 阶段 6：三个可运行示例）。

- 缺外部配置时打印精确缺失项并以退出码 2 结束（§23 启动检查）；
- 全量环境 + 注入 Fake 端口时三个示例均完整跑通（不发起真实网络）；
- 用户修正示例第二轮不重复调用 VLM（§25）。
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
from examples import _common, correction_example, image_example, text_example

from shijiajing_agent.config import Settings
from shijiajing_agent.contracts import AgentRequest
from tests.workflow.conftest import make_deps as make_fake_deps
from tests.workflow.conftest import two_candidate_result

# SHIJIAJING_* 外部配置清单（validate(require_real_adapters=True) 所需）
_REQUIRED_ENV = {
    "SHIJIAJING_ARK_API_KEY": "mock-key",
    "SHIJIAJING_ARK_BASE_URL": "https://mock-ark.example/v1",
    "SHIJIAJING_ARK_VISION_MODEL": "mock-vision",
    "SHIJIAJING_ARK_TEXT_MODEL": "mock-text",
    "SHIJIAJING_EMBEDDING_MODEL": "mock-embed",
    "SHIJIAJING_MILVUS_URI": "https://mock-milvus.example:19530",
    "SHIJIAJING_MILVUS_TOKEN": "mock-token",
    "SHIJIAJING_MILVUS_COLLECTION": "products_v1",
    "SHIJIAJING_CHECKPOINT_BACKEND": "sqlite",
    "SHIJIAJING_CHECKPOINT_DSN": "mock-dsn",
    "SHIJIAJING_TRACE_BACKEND": "structlog",
    "SHIJIAJING_TRACE_DSN": "mock-dsn",
    "SHIJIAJING_TAXONOMY_PATH": "mock-taxonomy",
    "SHIJIAJING_LOCAL_PRODUCT_SNAPSHOT_PATH": "mock-snapshot.jsonl",
}

_PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\x0dIHDR" + b"\x00" * 40


@pytest.fixture
def fake_deps(taxonomy: Any) -> tuple[Any, dict[str, Any]]:
    """Fake 端口依赖（不发起任何真实网络）。"""
    return make_fake_deps(taxonomy, Settings())


@pytest.fixture
def full_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in _REQUIRED_ENV.items():
        monkeypatch.setenv(name, value)


@pytest.fixture
def patch_make_deps(monkeypatch: pytest.MonkeyPatch, fake_deps: Any) -> dict[str, Any]:
    """把示例共用的 make_deps 替换为 Fake 装配。"""
    deps, fakes = fake_deps
    monkeypatch.setattr(_common, "make_deps", lambda settings: deps)
    return fakes


# ---------------------------------------------------------------------------
# _common：run_session / print_response / build_image_ref
# ---------------------------------------------------------------------------


def test_run_session_with_fake_deps(patch_make_deps: dict[str, Any]) -> None:
    patch_make_deps["retrieval"].sequence = [two_candidate_result()]
    responses = asyncio.run(
        _common.run_session(
            [AgentRequest(session_id="s-1", request_id="r-1", text="索尼耳机")],
            settings=Settings(),
        )
    )
    assert len(responses) == 1
    assert responses[0].status.value == "success"
    assert responses[0].groups, "检索命中的同款应产出比价组"


def test_print_response_renders(
    capsys: pytest.CaptureFixture[str], patch_make_deps: dict[str, Any]
) -> None:
    patch_make_deps["retrieval"].sequence = [two_candidate_result()]
    responses = asyncio.run(
        _common.run_session(
            [AgentRequest(session_id="s-1", request_id="r-1", text="索尼耳机")],
            settings=Settings(),
        )
    )
    _common.print_response(responses[0], index=1)
    out = capsys.readouterr().out
    assert "第 1 轮" in out
    assert "最低" in out


def test_build_image_ref_ok(tmp_path: Path) -> None:
    image = tmp_path / "photo.png"
    image.write_bytes(_PNG_BYTES)
    ref = _common.build_image_ref(str(image))
    assert ref.content_type.value == "image/png"
    assert ref.uri.startswith("data:image/png;base64,")
    assert len(ref.sha256) == 64


def test_build_image_ref_missing_file(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as excinfo:
        _common.build_image_ref(str(tmp_path / "nope.png"))
    assert excinfo.value.code == 2


def test_build_image_ref_bad_extension(tmp_path: Path) -> None:
    image = tmp_path / "photo.gif"
    image.write_bytes(_PNG_BYTES)
    with pytest.raises(SystemExit) as excinfo:
        _common.build_image_ref(str(image))
    assert excinfo.value.code == 2


# ---------------------------------------------------------------------------
# 配置缺失 → 退出码 2 + 精确缺失项
# ---------------------------------------------------------------------------


def test_text_example_missing_config_exits_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    for name in _REQUIRED_ENV:
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(SystemExit) as excinfo:
        text_example.main(["索尼耳机"])
    assert excinfo.value.code == 2
    err = capsys.readouterr().err
    assert "缺少必要配置" in err
    assert "SHIJIAJING_ARK_API_KEY" in err
    assert "SHIJIAJING_LOCAL_PRODUCT_SNAPSHOT_PATH" in err


def test_correction_example_requires_field() -> None:
    assert correction_example.main(["--image", "whatever.png"]) == 2


# ---------------------------------------------------------------------------
# 全量配置 + Fake 端口 → 完整跑通
# ---------------------------------------------------------------------------


def test_text_example_full_run(
    full_env: None, patch_make_deps: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    patch_make_deps["retrieval"].sequence = [two_candidate_result()]
    assert text_example.main(["索尼耳机", "只要黑色款"]) == 0
    out = capsys.readouterr().out
    assert "第 1 轮" in out
    assert "第 2 轮" in out
    assert "状态：" in out


def test_image_example_full_run(
    tmp_path: Path,
    full_env: None,
    patch_make_deps: dict[str, Any],
    capsys: pytest.CaptureFixture[str],
) -> None:
    image = tmp_path / "photo.png"
    image.write_bytes(_PNG_BYTES)
    patch_make_deps["retrieval"].sequence = [two_candidate_result()]
    assert image_example.main(["--image", str(image), "--text", "预算2000以内"]) == 0
    out = capsys.readouterr().out
    assert "第 1 轮" in out
    assert "识别：" in out  # VLM 识别结果被打印


def test_correction_example_full_run_no_second_vlm_call(
    tmp_path: Path,
    full_env: None,
    patch_make_deps: dict[str, Any],
) -> None:
    """两轮会话：修正后不再调用 VLM（§25 用户修正示例）。"""
    image = tmp_path / "photo.png"
    image.write_bytes(_PNG_BYTES)
    # 两轮各检索一次
    patch_make_deps["retrieval"].sequence = [two_candidate_result(), two_candidate_result()]
    assert (
        correction_example.main(["--image", str(image), "--brand", "Sony", "--model", "WH-1000XM5"])
        == 0
    )
    assert patch_make_deps["vision"].calls == 1, "修正轮不得再次调用 VLM"
