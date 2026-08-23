"""只读还原 Event Store 中的一次 Agent turn。"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from typing import Any

from shijiajing_agent.adapters.event_store import event_sort_key, make_event_store_adapter
from shijiajing_agent.asyncio_compat import run as run_async
from shijiajing_agent.contracts import AgentEventRecord
from shijiajing_agent.tools.cli_support import configure_utf8_output, public_error_message

_VERSION_FIELDS = (
    "prompt_version",
    "taxonomy_version",
    "retrieval_index_version",
    "fusion_version",
    "rerank_version",
)
_TERMINAL_EVENT_TYPES = frozenset({"agent_completed", "agent_failed"})


@dataclass(frozen=True)
class ReconstructedTurn:
    """Event Store 可还原的 turn 摘要和有序事件。"""

    session_id: str
    request_id: str
    turn_id: str
    trace_id: str
    event_count: int
    event_types: tuple[str, ...]
    agent_names: tuple[str, ...]
    node_names: tuple[str, ...]
    versions: dict[str, tuple[str, ...]]
    terminal_event_type: str | None
    events: tuple[AgentEventRecord, ...]

    def as_json(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "request_id": self.request_id,
            "turn_id": self.turn_id,
            "trace_id": self.trace_id,
            "event_count": self.event_count,
            "event_types": list(self.event_types),
            "agent_names": list(self.agent_names),
            "node_names": list(self.node_names),
            "versions": {key: list(values) for key, values in self.versions.items()},
            "terminal_event_type": self.terminal_event_type,
            "events": [event.model_dump(mode="json") for event in self.events],
        }


def reconstruct_turn(
    events: list[AgentEventRecord], *, request_id: str | None = None
) -> ReconstructedTurn:
    """校验并还原一个 turn；输入事件不会被修改。

    ``list_turn`` 已按统一事件时间线排序。这里再次排序，保证
    调用方直接传入数据库结果或测试事件时得到同一顺序。所有事件必须共享
    完整的 session/request/turn/trace 标识；缺失或混用标识直接失败，禁止
    用推测值拼接轨迹。
    """

    if not events:
        raise ValueError("没有可还原的 Event Store 事件")
    ordered = tuple(sorted(events, key=event_sort_key))
    first = ordered[0]
    if request_id is not None and first.request_id != request_id:
        raise ValueError("request_id 与 Event Store 事件不一致")
    identity = (first.session_id, first.request_id, first.turn_id, first.trace_id)
    if any(
        (event.session_id, event.request_id, event.turn_id, event.trace_id) != identity
        for event in ordered
    ):
        raise ValueError("同一 turn 的 Event Store 事件标识不一致")

    versions: dict[str, tuple[str, ...]] = {}
    for field in _VERSION_FIELDS:
        values = tuple(
            dict.fromkeys(
                str(value) for event in ordered if (value := event.payload.get(field)) is not None
            )
        )
        if values:
            versions[field] = values

    terminal = next(
        (
            event.event_type
            for event in reversed(ordered)
            if event.agent_name == "supervisor" and event.event_type in _TERMINAL_EVENT_TYPES
        ),
        None,
    )
    return ReconstructedTurn(
        session_id=first.session_id,
        request_id=first.request_id,
        turn_id=first.turn_id,
        trace_id=first.trace_id,
        event_count=len(ordered),
        event_types=tuple(dict.fromkeys(event.event_type for event in ordered)),
        agent_names=tuple(dict.fromkeys(event.agent_name for event in ordered)),
        node_names=tuple(dict.fromkeys(event.node_name for event in ordered if event.node_name)),
        versions=versions,
        terminal_event_type=terminal,
        events=ordered,
    )


async def _load_turn(
    *, backend: str, dsn: str, session_id: str, turn_id: str, request_id: str | None
) -> ReconstructedTurn:
    store = make_event_store_adapter(backend, dsn)
    if store is None:
        raise ValueError("Event Store backend 不能为 disabled")
    try:
        await store.setup()
        events = await store.list_turn(session_id, turn_id)
        return reconstruct_turn(events, request_id=request_id)
    finally:
        await store.close()


def _args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="shijiajing-reconstruct-turn")
    parser.add_argument("--dsn", help="Event Store DSN；默认读取 SHIJIAJING_EVENT_STORE_DSN")
    parser.add_argument(
        "--backend",
        choices=("sqlite", "postgres"),
        help="Event Store backend；默认读取 SHIJIAJING_EVENT_STORE_BACKEND",
    )
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--turn-id", required=True)
    parser.add_argument("--request-id")
    parser.add_argument("--json", action="store_true", help="输出完整机器可读 JSON")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    configure_utf8_output()
    args = _args(argv)
    dsn = args.dsn or os.environ.get("SHIJIAJING_EVENT_STORE_DSN")
    if not dsn:
        print("未配置 SHIJIAJING_EVENT_STORE_DSN，未执行还原。", file=sys.stderr)
        return 2
    backend = args.backend or os.environ.get("SHIJIAJING_EVENT_STORE_BACKEND", "sqlite")
    try:
        result = run_async(
            _load_turn(
                backend=backend,
                dsn=dsn,
                session_id=args.session_id,
                turn_id=args.turn_id,
                request_id=args.request_id,
            )
        )
    except Exception as exc:
        print(
            "事件还原失败："
            + public_error_message(exc, fallback="事件还原失败，请检查配置和事件存储"),
            file=sys.stderr,
        )
        return 2

    if args.json:
        print(json.dumps(result.as_json(), ensure_ascii=False, sort_keys=True))
    else:
        print(
            "事件还原成功："
            f"session_id={result.session_id} "
            f"request_id={result.request_id} "
            f"turn_id={result.turn_id} "
            f"trace_id={result.trace_id} "
            f"event_count={result.event_count}"
        )
        for event in result.events:
            node = event.node_name or "-"
            print(f"{event.occurred_at} {event.event_type} agent={event.agent_name} node={node}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
