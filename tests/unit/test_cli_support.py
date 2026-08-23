"""运维 CLI 公开错误边界测试。"""

from __future__ import annotations

from shijiajing_agent.errors import CheckpointUnavailableError
from shijiajing_agent.tools import cli_support
from shijiajing_agent.tools.cli_support import public_error_message


def test_configure_utf8_output_reconfigures_supported_streams(monkeypatch) -> None:
    class Stream:
        def __init__(self) -> None:
            self.calls: list[dict[str, str]] = []

        def reconfigure(self, **kwargs: str) -> None:
            self.calls.append(kwargs)

    stdout = Stream()
    stderr = Stream()
    monkeypatch.setattr(cli_support.sys, "stdout", stdout)
    monkeypatch.setattr(cli_support.sys, "stderr", stderr)

    cli_support.configure_utf8_output()

    expected = [{"encoding": "utf-8", "errors": "replace"}]
    assert stdout.calls == expected
    assert stderr.calls == expected


def test_public_error_message_keeps_safe_configuration_error() -> None:
    message = "二期配置错误：CHECKPOINT_DSN"

    assert public_error_message(ValueError(message), fallback="fallback") == message


def test_public_error_message_keeps_numeric_configuration_error() -> None:
    message = "配置错误：SHIJIAJING_TURN_TIMEOUT_SECONDS 必须是数字"

    assert public_error_message(ValueError(message), fallback="fallback") == message


def test_public_error_message_uses_domain_user_message() -> None:
    error = CheckpointUnavailableError(
        "postgresql://user:secret@db.internal/prod connection failed"
    )

    assert public_error_message(error, fallback="fallback") == "状态存储不可用"


def test_public_error_message_hides_raw_provider_details() -> None:
    error = RuntimeError("provider host=db.internal password=secret")

    result = public_error_message(error, fallback="外部资源不可用")

    assert result == "外部资源不可用"
    assert "secret" not in result
