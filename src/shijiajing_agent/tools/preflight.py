"""运行启动前的配置与持久化资源 preflight。"""

from __future__ import annotations

import argparse
import json
import sys
from contextlib import AsyncExitStack
from typing import Any

from shijiajing_agent.adapters.cache import make_cache_adapter
from shijiajing_agent.adapters.event_store import make_event_store_adapter
from shijiajing_agent.adapters.langgraph_persistence import open_graph_checkpointer
from shijiajing_agent.adapters.memory import make_memory_adapter
from shijiajing_agent.adapters.observability import make_trace_sink
from shijiajing_agent.adapters.request_ledger import make_request_ledger
from shijiajing_agent.asyncio_compat import run as run_async
from shijiajing_agent.config import Settings, load_settings
from shijiajing_agent.contracts import AgentEvent, EventType, NodeStatus, now_iso
from shijiajing_agent.runtime import open_resource
from shijiajing_agent.tools.cli_support import configure_utf8_output, public_error_message


def _checked_resource_names(settings: Settings) -> list[str]:
    names = ["multi_agent_checkpointer"]
    if settings.request_ledger_backend != "disabled":
        names.append("request_ledger")
    if settings.memory_backend != "disabled":
        names.append("memory")
    if settings.cache_backend != "disabled":
        names.append("cache")
    if settings.event_store_backend != "disabled":
        names.append("event_store")
    names.append("trace")
    return names


def _trace_probe_event(event_type: EventType) -> AgentEvent:
    return AgentEvent(
        session_id="preflight",
        request_id="preflight-trace-probe",
        turn_id="preflight-trace-probe",
        trace_id="preflight-trace-probe",
        event_type=event_type,
        timestamp=now_iso(),
        node_name=None,
        status=NodeStatus.SUCCESS,
    )


async def run_preflight(
    settings: Settings, *, require_real_adapters: bool = True, verify_trace: bool = False
) -> dict[str, Any]:
    """校验配置并完成已启用存储资源的 setup/close 生命周期。"""
    if require_real_adapters:
        missing = settings.validate(require_real_adapters=True)
        if missing:
            names = ", ".join(f"SHIJIAJING_{name}" for name in missing)
            raise ValueError(f"缺少必要配置：{names}")
    engineering_errors = settings.validate_engineering()
    if engineering_errors:
        raise ValueError("二期配置错误：" + ", ".join(engineering_errors))
    if verify_trace and settings.trace_backend != "opentelemetry":
        raise ValueError("--verify-trace 要求 SHIJIAJING_TRACE_BACKEND=opentelemetry")

    async with AsyncExitStack() as stack:
        await stack.enter_async_context(open_graph_checkpointer(settings))
        await open_resource(
            stack,
            make_request_ledger(
                settings.request_ledger_backend,
                settings.request_ledger_dsn or settings.checkpoint_dsn,
                pool_min_size=settings.postgres_pool_min_size,
                pool_max_size=settings.postgres_pool_max_size,
                pool_timeout_seconds=settings.postgres_pool_timeout_seconds,
            ),
        )
        await open_resource(
            stack,
            make_memory_adapter(
                settings.memory_backend,
                settings.memory_dsn,
                pool_min_size=settings.postgres_pool_min_size,
                pool_max_size=settings.postgres_pool_max_size,
                pool_timeout_seconds=settings.postgres_pool_timeout_seconds,
            ),
        )
        await open_resource(
            stack,
            make_cache_adapter(
                settings.cache_backend,
                settings.cache_dsn,
                pool_min_size=settings.postgres_pool_min_size,
                pool_max_size=settings.postgres_pool_max_size,
                pool_timeout_seconds=settings.postgres_pool_timeout_seconds,
            ),
        )
        await open_resource(
            stack,
            make_event_store_adapter(
                settings.event_store_backend,
                settings.event_store_dsn,
                pool_min_size=settings.postgres_pool_min_size,
                pool_max_size=settings.postgres_pool_max_size,
                pool_timeout_seconds=settings.postgres_pool_timeout_seconds,
            ),
        )
        trace = make_trace_sink(settings)
        await open_resource(stack, trace)
        if verify_trace:
            await trace.emit(_trace_probe_event(EventType.TURN_STARTED))
            await trace.emit(_trace_probe_event(EventType.RESULTS_READY))

    return {
        "status": "ok",
        "checked_resources": [
            *_checked_resource_names(settings),
            *(["trace_probe"] if verify_trace else []),
        ],
        "checkpoint_backend": settings.checkpoint_backend,
        "request_ledger_backend": settings.request_ledger_backend,
        "memory_enabled": settings.memory_enabled,
        "memory_recall_enabled": settings.memory_recall_enabled,
        "memory_commit_enabled": settings.memory_commit_enabled,
        "memory_backend": settings.memory_backend,
        "cache_backend": settings.cache_backend,
        "event_store_backend": settings.event_store_backend,
        "trace_backend": settings.trace_backend,
        "hitl_enabled": settings.hitl_enabled,
        "memory_confirmation_required": settings.memory_confirmation_required,
        "retrieval_fusion_strategy": settings.retrieval_fusion_strategy,
        "retrieval_rerank_enabled": settings.retrieval_rerank_enabled,
        "retrieval_index_version": settings.retrieval_index_version,
        "cache_ttl_seconds": {
            "vision": settings.vision_cache_ttl_seconds,
            "intent": settings.intent_cache_ttl_seconds,
            "query_rewrite": settings.query_rewrite_cache_ttl_seconds,
            "retrieval": settings.retrieval_cache_ttl_seconds,
            "explanation": settings.explanation_cache_ttl_seconds,
            "product_canonicalization": settings.product_canonicalization_cache_ttl_seconds,
        },
        "trace_verified": verify_trace,
        "postgres_pool": {
            "min_size": settings.postgres_pool_min_size,
            "max_size": settings.postgres_pool_max_size,
            "timeout_seconds": settings.postgres_pool_timeout_seconds,
        },
    }


def _args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="shijiajing-preflight")
    parser.add_argument(
        "--storage-only",
        action="store_true",
        help="只校验二期配置和持久化资源，不要求模型/检索应用配置",
    )
    parser.add_argument(
        "--verify-trace",
        action="store_true",
        help="发送无业务数据的合成 turn span，验证 OpenTelemetry endpoint 接收",
    )
    parser.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    return parser.parse_args(argv)


def _public_error_message(exc: Exception) -> str:
    """返回 CLI 可公开的错误，不把 provider/DSN 异常原文带出进程。"""
    return public_error_message(exc, fallback="启动前检查失败，请检查配置和外部服务")


def main(argv: list[str] | None = None) -> int:
    configure_utf8_output()
    args = _args(argv)
    try:
        result = run_async(
            run_preflight(
                load_settings(),
                require_real_adapters=not args.storage_only,
                verify_trace=args.verify_trace,
            )
        )
        if args.json:
            print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        else:
            print("preflight 通过：" + ", ".join(result["checked_resources"]))
        return 0
    except Exception as exc:
        public_error = _public_error_message(exc)
        if args.json:
            print(json.dumps({"status": "failed", "error": public_error}, ensure_ascii=False))
        else:
            print(f"preflight 失败：{public_error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
