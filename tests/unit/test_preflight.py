"""preflight 的配置校验与 SQLite/native setup 回归。"""

from __future__ import annotations

import json

import pytest

from shijiajing_agent.config import Settings
from shijiajing_agent.errors import CheckpointUnavailableError
from shijiajing_agent.tools import preflight
from shijiajing_agent.tools.preflight import _public_error_message, run_preflight


@pytest.mark.asyncio
async def test_preflight_checks_native_sqlite_resources(tmp_path) -> None:
    settings = Settings(
        checkpoint_backend="sqlite",
        checkpoint_dsn=str(tmp_path / "checkpoint.db"),
        request_ledger_backend="sqlite",
        request_ledger_dsn=str(tmp_path / "ledger.db"),
        trace_backend="structlog",
    )

    result = await run_preflight(settings, require_real_adapters=False)

    assert result["status"] == "ok"
    assert result["memory_enabled"] is False
    assert result["memory_recall_enabled"] is True
    assert result["memory_commit_enabled"] is True
    assert result["hitl_enabled"] is False
    assert result["memory_confirmation_required"] is True
    assert result["retrieval_fusion_strategy"] == "weighted"
    assert result["retrieval_rerank_enabled"] is False
    assert result["retrieval_index_version"] is None
    assert result["cache_ttl_seconds"] == {
        "vision": 2_592_000,
        "intent": 604_800,
        "query_rewrite": 604_800,
        "retrieval": 300,
        "explanation": 86_400,
        "product_canonicalization": 604_800,
    }
    assert result["postgres_pool"] == {
        "min_size": 1,
        "max_size": 4,
        "timeout_seconds": 30.0,
    }
    assert result["checked_resources"] == [
        "multi_agent_checkpointer",
        "request_ledger",
        "trace",
    ]


@pytest.mark.asyncio
async def test_preflight_reports_exact_missing_application_config() -> None:
    with pytest.raises(ValueError, match="SHIJIAJING_ARK_API_KEY"):
        await run_preflight(Settings())


@pytest.mark.asyncio
async def test_preflight_trace_probe_requires_opentelemetry() -> None:
    settings = Settings(
        checkpoint_backend="sqlite",
        checkpoint_dsn="checkpoint.db",
        request_ledger_backend="sqlite",
        request_ledger_dsn="ledger.db",
        trace_backend="structlog",
    )

    with pytest.raises(ValueError, match="TRACE_BACKEND=opentelemetry"):
        await run_preflight(settings, require_real_adapters=False, verify_trace=True)


@pytest.mark.asyncio
async def test_preflight_trace_probe_emits_synthetic_turn(monkeypatch, tmp_path) -> None:
    class FakeTrace:
        def __init__(self) -> None:
            self.events = []

        async def setup(self) -> None:
            return None

        async def emit(self, event) -> None:
            self.events.append(event)

        def close(self) -> None:
            return None

    trace = FakeTrace()
    monkeypatch.setattr(preflight, "make_trace_sink", lambda settings: trace)
    settings = Settings(
        checkpoint_backend="sqlite",
        checkpoint_dsn=str(tmp_path / "checkpoint.db"),
        request_ledger_backend="sqlite",
        request_ledger_dsn=str(tmp_path / "ledger.db"),
        trace_backend="opentelemetry",
        trace_dsn="http://collector.example/v1/traces",
    )

    result = await run_preflight(settings, require_real_adapters=False, verify_trace=True)

    assert result["trace_verified"] is True
    assert result["checked_resources"][-1] == "trace_probe"
    assert [event.event_type for event in trace.events] == [
        "turn_started",
        "results_ready",
    ]
    assert all(event.session_id == "preflight" for event in trace.events)


def test_preflight_public_error_keeps_configuration_fields_but_hides_provider_details() -> None:
    configuration = "缺少必要配置：SHIJIAJING_CHECKPOINT_DSN"
    assert _public_error_message(ValueError(configuration)) == configuration
    assert (
        _public_error_message(
            CheckpointUnavailableError(
                "checkpoint 连接失败: postgresql://user:secret@db.internal/prod"
            )
        )
        == "状态存储不可用"
    )
    assert (
        _public_error_message(RuntimeError("provider returned password=secret host=db.internal"))
        == "启动前检查失败，请检查配置和外部服务"
    )


def test_preflight_json_error_does_not_expose_raw_exception(monkeypatch, capsys) -> None:
    async def fail(*args, **kwargs):
        raise RuntimeError("connection failed for postgresql://user:secret@db.internal/prod")

    monkeypatch.setattr(preflight, "run_preflight", fail)

    assert preflight.main(["--storage-only", "--json"]) == 2

    output = json.loads(capsys.readouterr().out)
    assert output == {"status": "failed", "error": "启动前检查失败，请检查配置和外部服务"}
    assert "secret" not in json.dumps(output, ensure_ascii=False)


def test_preflight_json_keeps_exact_numeric_configuration_error(monkeypatch, capsys) -> None:
    monkeypatch.setenv("SHIJIAJING_TURN_TIMEOUT_SECONDS", "fast")

    assert preflight.main(["--storage-only", "--json"]) == 2

    output = json.loads(capsys.readouterr().out)
    assert output == {
        "status": "failed",
        "error": "配置错误：SHIJIAJING_TURN_TIMEOUT_SECONDS 必须是数字",
    }
