"""LangGraph 1.x 原生异步 Checkpointer 装配。

SQLite 的 `from_conn_string()` 不接受 serde，因此这里显式管理 aiosqlite connection；
PostgreSQL 使用当前锁定版本提供的 `serde` 参数。两条路径都在 yield 前完成 setup。
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from shijiajing_agent.config import Settings
from shijiajing_agent.persistence_safety import sanitize_persisted_value

_CONTRACT_NAMES = (
    "AgentStatus",
    "EventType",
    "ConstraintSource",
    "SortBy",
    "Preference",
    "ImageContentType",
    "SellerType",
    "NodeStatus",
    "CompletionReason",
    "ImageRef",
    "RecognitionCorrection",
    "AgentRequest",
    "AgentExecutionContext",
    "RecognitionResult",
    "MemoryOperation",
    "MemoryApplyMode",
    "MemoryStatus",
    "MemoryDirective",
    "IntentPatch",
    "MemoryRecord",
    "MemoryQuery",
    "MemoryMutation",
    "SpecialistAgentName",
    "AgentTaskKind",
    "AgentTaskBudget",
    "AgentTaskError",
    "AgentTaskUsage",
    "AgentTaskV2",
    "AgentResultV2",
    "RecognitionTaskInput",
    "IntentTaskInput",
    "RetrievalTaskInput",
    "ExplanationTaskInput",
    "MemoryTaskInput",
    "RecognitionTaskOutput",
    "IntentTaskOutput",
    "RetrievalTaskOutput",
    "ExplanationTaskOutput",
    "MemoryTaskOutput",
    "HandoffRequest",
    "TaskRecord",
    "SupervisorBudgetUsage",
    "CanonicalUnderstanding",
    "ExecutionPlan",
    "SupervisorPlanningInput",
    "SupervisorReplanningInput",
    "ExecutionPlanPatch",
    "SourcedValue",
    "ShoppingConstraints",
    "HardFilters",
    "RetrievalQuery",
    "RetrievalMode",
    "Offer",
    "RetrievalCandidate",
    "NormalizedCandidate",
    "MatchPair",
    "SkuGroup",
    "ClarificationOption",
    "Clarification",
    "RankedGroup",
    "AgentResponse",
    "InterruptKind",
    "AgentInterrupt",
    "AgentResume",
    "AgentTurnResult",
    "ConversationTurnSummary",
    "AgentEvent",
    "AgentEventRecord",
)
_ALLOWED_MODULES = tuple(
    [("shijiajing_agent.contracts", name) for name in _CONTRACT_NAMES]
    + [
        ("shijiajing_agent.domain.evidence", "EvidenceBundle"),
        ("shijiajing_agent.domain.evidence", "GroupEvidence"),
    ]
)


class _RedactingJsonPlusSerializer(JsonPlusSerializer):
    """LangGraph native serializer：先脱敏再编码，禁止原始输入进入 checkpoint。"""

    def dumps_typed(self, obj: Any) -> tuple[str, bytes]:
        return super().dumps_typed(sanitize_persisted_value(obj))

    def loads_typed(self, data: tuple[str, bytes]) -> Any:
        return sanitize_persisted_value(super().loads_typed(data))


def _serializer() -> JsonPlusSerializer:
    return _RedactingJsonPlusSerializer(
        pickle_fallback=False,
        allowed_json_modules=_ALLOWED_MODULES,
        allowed_msgpack_modules=_ALLOWED_MODULES,
    )


def _sqlite_path(dsn: str) -> str:
    path = dsn
    for prefix in ("sqlite:///", "sqlite://"):
        if path.startswith(prefix):
            return path[len(prefix) :]
    return path


@asynccontextmanager
async def open_graph_checkpointer(
    settings: Settings,
) -> AsyncGenerator[BaseCheckpointSaver[str], None]:
    """打开并初始化 native checkpointer；资源生命周期由调用方上下文持有。"""

    backend = settings.checkpoint_backend.lower()
    dsn = settings.checkpoint_dsn or ""
    if backend == "sqlite":
        if not dsn:
            raise ValueError("SHIJIAJING_CHECKPOINT_DSN 不能为空")
        import aiosqlite
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

        async with aiosqlite.connect(_sqlite_path(dsn)) as connection:
            saver = AsyncSqliteSaver(connection, serde=_serializer())
            await saver.setup()
            yield saver
        return

    if backend == "postgres":
        if not dsn:
            raise ValueError("SHIJIAJING_CHECKPOINT_DSN 不能为空")
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        async with AsyncPostgresSaver.from_conn_string(dsn, serde=_serializer()) as saver:
            await saver.setup()
            yield saver
        return

    raise ValueError(f"未知 graph persistence backend: {settings.checkpoint_backend}")
