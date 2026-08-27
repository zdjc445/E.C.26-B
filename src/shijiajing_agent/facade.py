"""Agent 门面（方案 §17、§18）。

职责：
 - ``request_id`` 全局幂等：重复请求返回已保存响应，不重复调用外部依赖。
 - 同一 ``session_id`` 串行执行；Checkpoint 乐观版本检查，冲突整轮最多重放一次。
 - 每个节点完成后保存 super-step 状态；进程中断后从最近成功点恢复。
- 最大步数与整轮超时保护（§9.3、§18）：超限转为 FAILED 响应，保留 trace。
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any, cast

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.types import Command

from shijiajing_agent.adapters.ark_models import load_prompt
from shijiajing_agent.adapters.event_store import stable_event_id
from shijiajing_agent.config import Settings
from shijiajing_agent.contracts import (
    AgentEvent,
    AgentEventRecord,
    AgentExecutionContext,
    AgentInterrupt,
    AgentRequest,
    AgentResponse,
    AgentResume,
    AgentStatus,
    AgentTurnResult,
    CompletionReason,
    EventType,
    NodeStatus,
    content_hash,
    now_iso,
)
from shijiajing_agent.domain.taxonomy import Taxonomy
from shijiajing_agent.errors import (
    CheckpointUnavailableError,
    ErrorCode,
    RequestLedgerUnavailableError,
    SessionConflictError,
    WorkflowStepLimitError,
)
from shijiajing_agent.graph import build_graph, stream_values
from shijiajing_agent.nodes.input_nodes import make_initial_state, make_native_turn_input
from shijiajing_agent.nodes.memory_nodes import append_turn_summary_node
from shijiajing_agent.ports.cache import VersionedCachePort
from shijiajing_agent.ports.checkpoint import CheckpointPort
from shijiajing_agent.ports.dependencies import SupervisorPlannerPort
from shijiajing_agent.ports.event_store import EventStorePort
from shijiajing_agent.ports.memory import MemoryPort
from shijiajing_agent.ports.models import (
    DynamicProductCanonicalizationPort,
    DynamicSchemaInductionPort,
    ExplanationModelPort,
    IntentModelPort,
    ProductCanonicalizationPort,
    QueryRewritePort,
    VisionModelPort,
)
from shijiajing_agent.ports.observability import MetricsPort, TraceSinkPort
from shijiajing_agent.ports.request_ledger import RequestLedgerPort
from shijiajing_agent.ports.retrieval import ProductRetrievalPort
from shijiajing_agent.state import AgentState, NativeTurnInput

_CHECKPOINT_RETRIES = 2
_MODEL_PROMPTS = {
    "recognize_image": ("vision.md", "ark_vision_model"),
    "parse_intent": ("intent.md", "ark_text_model"),
    "parse_intent_resume": ("intent.md", "ark_text_model"),
    "rewrite_query": ("query_rewrite.md", "ark_text_model"),
    "canonicalize_products": ("product_canonicalization.md", "ark_text_model"),
    "generate_explanation": ("explanation.md", "ark_text_model"),
}
_AGENT_NAMES = {
    "recognize_image": "recognition",
    "parse_intent": "intent",
    "parse_intent_resume": "intent",
    "rewrite_query": "retrieval",
    "retrieve_candidates": "retrieval",
    "relax_recognition_constraints": "retrieval",
    "normalize_candidates": "retrieval",
    "match_same_item": "retrieval",
    "split_sku": "retrieval",
    "rank_groups": "retrieval",
    "build_no_results": "retrieval",
    "build_failed_response": "retrieval",
    "recognition_subgraph": "recognition",
    "intent_subgraph": "intent",
    "retrieval_subgraph": "retrieval",
    "explanation_subgraph": "explanation",
    "memory_subgraph": "memory",
    "build_evidence": "explanation",
    "generate_explanation": "explanation",
    "recall_memory": "memory",
    "prepare_memory_mutations": "memory",
    "commit_memory": "memory",
    "append_turn_summary": "memory",
}
_AGENT_TERMINAL_NODES = {
    "recognition": frozenset({"normalize_recognition"}),
    "intent": frozenset({"parse_intent", "parse_intent_resume"}),
    "retrieval": frozenset({"rank_groups", "build_no_results", "build_failed_response"}),
    "explanation": frozenset({"generate_explanation"}),
    "memory": frozenset({"append_turn_summary"}),
}


@dataclass
class AgentDependencies:
    """端口与运行参数容器。测试与生产共用同一装配入口。"""

    taxonomy: Taxonomy
    settings: Settings
    vision: VisionModelPort
    intent: IntentModelPort
    query_rewrite: QueryRewritePort
    explanation: ExplanationModelPort
    retrieval: ProductRetrievalPort
    checkpoint: CheckpointPort
    trace: TraceSinkPort
    metrics: MetricsPort
    graph_checkpointer: BaseCheckpointSaver[str] | None = None
    request_ledger: RequestLedgerPort | None = None
    memory: MemoryPort | None = None
    cache: VersionedCachePort | None = None
    event_store: EventStorePort | None = None
    supervisor_planner: SupervisorPlannerPort | None = None
    product_canonicalizer: ProductCanonicalizationPort | None = None
    dynamic_schema_inducer: DynamicSchemaInductionPort | None = None
    dynamic_product_canonicalizer: DynamicProductCanonicalizationPort | None = None


class AgentFacade:
    def __init__(self, deps: AgentDependencies) -> None:
        self._deps = deps
        self._graph = build_graph(deps)
        self._locks: dict[str, asyncio.Lock] = {}
        self._trace_started_turns: set[tuple[str, str]] = set()
        self._agent_lifecycle_events: set[tuple[str, str, str, str]] = set()

    @property
    def dependencies(self) -> AgentDependencies:
        """返回 runtime 所有者装配的依赖视图；资源生命周期仍由 runtime 管理。"""
        return self._deps

    # ------------------------------------------------------------------
    async def run(self, request: AgentRequest) -> AgentResponse:
        """执行一轮 Agent turn。幂等、串行、超时与步数保护都在这里。"""
        if self._deps.settings.orchestration_mode != "workflow":
            return await self._run_multi_agent(request, AgentExecutionContext())
        session_id = request.session_id
        settings = self._deps.settings

        try:
            cached = await self._ledger_get(session_id, request.request_id)
        except RequestLedgerUnavailableError:
            return self._bare_failed_response(
                request,
                ErrorCode.REQUEST_LEDGER_UNAVAILABLE,
                "请求结果账本不可用，请稍后重试。",
            )
        if cached is not None:
            return cached

        # 幂等：进入会话锁前先查一次已保存响应。
        cached = await self._load_cached(session_id, request.request_id)
        if cached is not None:
            return cached

        async with self._session_lock(session_id):
            # 持锁后再查一次：并发窗口内可能有其他任务已完成
            try:
                cached = await self._ledger_get(session_id, request.request_id)
            except RequestLedgerUnavailableError:
                return self._bare_failed_response(
                    request,
                    ErrorCode.REQUEST_LEDGER_UNAVAILABLE,
                    "请求结果账本不可用，请稍后重试。",
                )
            if cached is not None:
                return cached
            cached = await self._load_cached(session_id, request.request_id)
            if cached is not None:
                return cached

            try:
                prev = await self._checkpoint_load(session_id)
            except CheckpointUnavailableError:
                return self._bare_failed_response(
                    request, ErrorCode.CHECKPOINT_UNAVAILABLE, "状态存储不可用，请稍后重试。"
                )

            try:
                async with asyncio.timeout(settings.turn_timeout_seconds):
                    response, _ = await self._run_once(request, prev)
                await self._ledger_save(session_id, request.request_id, response)
                return response
            except SessionConflictError:
                # 乐观版本冲突：整轮最多重放一次。
                try:
                    prev = await self._checkpoint_load(session_id)
                except CheckpointUnavailableError:
                    prev = None
                try:
                    async with asyncio.timeout(settings.turn_timeout_seconds):
                        response, _ = await self._run_once(request, prev)
                    await self._ledger_save(session_id, request.request_id, response)
                    return response
                except SessionConflictError:
                    return self._bare_failed_response(
                        request, ErrorCode.SESSION_CONFLICT, "会话状态冲突，请重试。"
                    )
            except TimeoutError:
                return self._bare_failed_response(
                    request, ErrorCode.TURN_TIMEOUT, "处理超时，请稍后重试。"
                )
            except RequestLedgerUnavailableError:
                return self._bare_failed_response(
                    request,
                    ErrorCode.REQUEST_LEDGER_UNAVAILABLE,
                    "请求结果账本不可用，请稍后重试。",
                )

    async def start(self, request: AgentRequest, context: AgentExecutionContext) -> AgentTurnResult:
        """native thread start；没有 native runtime 时兼容包装 legacy run。"""
        if self._deps.settings.orchestration_mode != "workflow":
            return await self._start_multi_agent(request, context)
        if context.memory_enabled and context.memory_owner_id is None:
            return AgentTurnResult(
                response=self._bare_failed_response(
                    request,
                    ErrorCode.INVALID_REQUEST,
                    "启用记忆时必须提供可信 memory_owner_id。",
                )
            )
        if self._deps.graph_checkpointer is None:
            if context.memory_enabled:
                return AgentTurnResult(
                    response=self._bare_failed_response(
                        request,
                        ErrorCode.INVALID_REQUEST,
                        "启用记忆需要 native persistence，请使用 native runtime。",
                    )
                )
            return AgentTurnResult(response=await self.run(request))
        session_id = request.session_id
        try:
            cached = await self._ledger_get(session_id, request.request_id)
            if cached is not None:
                return AgentTurnResult(response=cached)
        except RequestLedgerUnavailableError:
            return AgentTurnResult(
                response=self._bare_failed_response(
                    request,
                    ErrorCode.REQUEST_LEDGER_UNAVAILABLE,
                    "请求结果账本不可用，请稍后重试。",
                )
            )

        async with self._session_lock(session_id):
            try:
                cached = await self._ledger_get(session_id, request.request_id)
            except RequestLedgerUnavailableError:
                return AgentTurnResult(
                    response=self._bare_failed_response(
                        request,
                        ErrorCode.REQUEST_LEDGER_UNAVAILABLE,
                        "请求结果账本不可用，请稍后重试。",
                    )
                )
            if cached is not None:
                return AgentTurnResult(response=cached)
            config: RunnableConfig = {"configurable": {"thread_id": session_id}}
            try:
                snapshot = await self._graph.aget_state(config)
            except Exception:
                return AgentTurnResult(
                    response=self._bare_failed_response(
                        request,
                        ErrorCode.CHECKPOINT_UNAVAILABLE,
                        "状态存储不可用，请稍后重试。",
                    )
                )
            values: dict[str, Any] = dict(snapshot.values)
            active = self._interrupt_of(values) or self._interrupt_from_snapshot(snapshot)
            if active is not None:
                if active.request_id != request.request_id:
                    return AgentTurnResult(
                        response=self._bare_failed_response(
                            request,
                            ErrorCode.INVALID_REQUEST,
                            "当前 session 存在待恢复 interrupt，请先 resume。",
                        )
                    )
                raw_original_context = values.get("execution_context")
                try:
                    if isinstance(raw_original_context, AgentExecutionContext):
                        original_context = raw_original_context
                    elif isinstance(raw_original_context, Mapping):
                        original_context = AgentExecutionContext.model_validate(
                            raw_original_context
                        )
                    elif raw_original_context is None:
                        original_context = None
                    else:
                        raise ValueError("execution_context 格式无效")
                except Exception:
                    original_context = None
                    context_mismatch = True
                else:
                    context_mismatch = (
                        original_context is None and context != AgentExecutionContext()
                    ) or (original_context is not None and original_context != context)
                if context_mismatch:
                    return AgentTurnResult(
                        response=self._bare_failed_response(
                            request,
                            ErrorCode.INVALID_REQUEST,
                            "execution_context 与原请求不一致。",
                        )
                    )
                return AgentTurnResult(interrupt=active)
            stored_request_id = str(values.get("request_id") or "")
            stored_response = self._response_of(values)
            if stored_request_id == request.request_id and stored_response is not None:
                if self._deps.request_ledger is not None:
                    try:
                        await self._ledger_save(session_id, request.request_id, stored_response)
                    except RequestLedgerUnavailableError:
                        return AgentTurnResult(
                            response=self._bare_failed_response(
                                request,
                                ErrorCode.REQUEST_LEDGER_UNAVAILABLE,
                                "请求结果账本不可用，请稍后重试。",
                            )
                        )
                    await self._record_ledger_repair(stored_response)
                return AgentTurnResult(response=stored_response)
            input_state: NativeTurnInput = make_native_turn_input(request)
            input_state["execution_context"] = context
            last_state: AgentState = input_state  # type: ignore[assignment]
            turn_id = str(input_state.get("turn_id") or "")
            trace_id = str(input_state.get("trace_id") or "")
            await self._ensure_turn_started(
                session_id=session_id,
                request_id=request.request_id,
                turn_id=turn_id,
                trace_id=trace_id,
            )
            emitted_node_events = 0
            node_attempts: dict[str, int] = {}
            graph_finished = False
            try:
                async with asyncio.timeout(self._deps.settings.turn_timeout_seconds):
                    async for snapshot in stream_values(self._graph, input_state, config):
                        last_state = snapshot
                        emitted_node_events = await self._emit_snapshot_node_events(
                            snapshot, emitted_node_events, node_attempts
                        )
                graph_finished = True
                interrupt = self._interrupt_of(last_state)
                if interrupt is not None:
                    await self._append_audit_event(
                        session_id=session_id,
                        request_id=request.request_id,
                        turn_id=turn_id,
                        trace_id=trace_id,
                        event_type="agent_interrupted",
                        sequence=len(last_state.get("node_events") or []),
                        payload={
                            "interrupt_id": interrupt.interrupt_id,
                            "interrupt_kind": interrupt.kind.value,
                        },
                    )
                    return AgentTurnResult(interrupt=interrupt)
                response = self._response_of(last_state)
                if response is None:
                    response = self._bare_failed_response(
                        request, ErrorCode.INTERNAL_ERROR, "native workflow 未产出响应。"
                    ).model_copy(update={"turn_id": turn_id, "trace_id": trace_id})
                    await self._persist_native_failed_state(
                        config,
                        last_state,
                        request,
                        response,
                        ErrorCode.INTERNAL_ERROR,
                        "native workflow 未产出响应。",
                    )
                await self._ledger_save(session_id, request.request_id, response)
                await self._emit_terminal_event(response)
                return AgentTurnResult(response=response)
            except RequestLedgerUnavailableError:
                failed = self._bare_failed_response(
                    request,
                    ErrorCode.REQUEST_LEDGER_UNAVAILABLE,
                    "请求结果账本不可用，请稍后重试。",
                ).model_copy(update={"turn_id": turn_id, "trace_id": trace_id})
                await self._emit_terminal_event(failed)
                return AgentTurnResult(response=failed)
            except TimeoutError:
                failed = self._bare_failed_response(
                    request, ErrorCode.TURN_TIMEOUT, "处理超时，请稍后重试。"
                ).model_copy(update={"turn_id": turn_id, "trace_id": trace_id})
                if not graph_finished:
                    await self._persist_native_failed_state(
                        config,
                        last_state,
                        request,
                        failed,
                        ErrorCode.TURN_TIMEOUT,
                        "处理超时，请稍后重试。",
                    )
                try:
                    await self._ledger_save(session_id, request.request_id, failed)
                except RequestLedgerUnavailableError:
                    pass
                await self._emit_terminal_event(failed)
                return AgentTurnResult(response=failed)
            except Exception as exc:
                failed = self._bare_failed_response(
                    request, ErrorCode.INTERNAL_ERROR, "处理失败，请稍后重试。"
                ).model_copy(update={"turn_id": turn_id, "trace_id": trace_id})
                if not graph_finished:
                    await self._emit_agent_failure_from_exception(last_state, exc)
                    await self._persist_native_failed_state(
                        config,
                        last_state,
                        request,
                        failed,
                        ErrorCode.INTERNAL_ERROR,
                        "处理失败，请稍后重试。",
                    )
                try:
                    await self._ledger_save(session_id, request.request_id, failed)
                except RequestLedgerUnavailableError:
                    pass
                await self._emit_terminal_event(failed)
                return AgentTurnResult(response=failed)

    async def resume(
        self,
        session_id: str,
        resume: AgentResume,
        context: AgentExecutionContext,
    ) -> AgentTurnResult:
        """恢复 native interrupt；校验 interrupt_id、session 和 owner 后执行一次。"""
        if self._deps.settings.orchestration_mode != "workflow":
            return await self._resume_multi_agent(session_id, resume, context)
        if self._deps.graph_checkpointer is None:
            request = AgentRequest.model_validate(
                {"session_id": session_id, "request_id": "resume", "text": "resume"}
            )
            return AgentTurnResult(
                response=self._bare_failed_response(
                    request, ErrorCode.INVALID_REQUEST, "native persistence 未启用，不能 resume。"
                )
            )
        config: RunnableConfig = {"configurable": {"thread_id": session_id}}
        async with self._session_lock(session_id):
            try:
                snapshot = await self._graph.aget_state(config)
            except Exception:
                request = AgentRequest.model_validate(
                    {"session_id": session_id, "request_id": "resume", "text": "resume"}
                )
                return AgentTurnResult(
                    response=self._bare_failed_response(
                        request,
                        ErrorCode.CHECKPOINT_UNAVAILABLE,
                        "状态存储不可用，请稍后重试。",
                    )
                )
            values = dict(snapshot.values)
            active = self._interrupt_of(values) or self._interrupt_from_snapshot(snapshot)
            request_id = str(values.get("request_id") or "resume")
            request = AgentRequest.model_validate(
                {"session_id": session_id, "request_id": request_id, "text": "resume"}
            )
            if context.memory_enabled and context.memory_owner_id is None:
                return AgentTurnResult(
                    response=self._bare_failed_response(
                        request,
                        ErrorCode.INVALID_REQUEST,
                        "启用记忆时必须提供可信 memory_owner_id。",
                    )
                )
            if (
                active is None
                or active.session_id != session_id
                or active.request_id != request_id
                or active.interrupt_id != resume.interrupt_id
            ):
                return AgentTurnResult(
                    response=self._bare_failed_response(
                        request, ErrorCode.INVALID_REQUEST, "interrupt_id 不匹配或不存在。"
                    )
                )
            stored_active = self._interrupt_of(values)
            if values.get("resume_consumed") and (
                stored_active is not None and stored_active.interrupt_id == active.interrupt_id
            ):
                return AgentTurnResult(
                    response=self._bare_failed_response(
                        request, ErrorCode.INVALID_REQUEST, "interrupt 已经恢复过。"
                    )
                )
            raw_original_context = values.get("execution_context")
            try:
                if isinstance(raw_original_context, AgentExecutionContext):
                    original_context = raw_original_context
                elif isinstance(raw_original_context, Mapping):
                    original_context = AgentExecutionContext.model_validate(raw_original_context)
                elif raw_original_context is None:
                    original_context = None
                else:
                    raise ValueError("execution_context 格式无效")
            except Exception:
                original_context = None
                context_mismatch = True
            else:
                context_mismatch = (
                    original_context is None and context != AgentExecutionContext()
                ) or (original_context is not None and original_context != context)
            if context_mismatch:
                return AgentTurnResult(
                    response=self._bare_failed_response(
                        request, ErrorCode.INVALID_REQUEST, "execution_context 与原请求不一致。"
                    )
                )
            try:
                claimed = await self._deps.checkpoint.claim_resume(session_id, active.interrupt_id)
            except Exception:
                return AgentTurnResult(
                    response=self._bare_failed_response(
                        request,
                        ErrorCode.CHECKPOINT_UNAVAILABLE,
                        "resume 幂等存储不可用，请稍后重试。",
                    )
                )
            if not claimed:
                return AgentTurnResult(
                    response=self._bare_failed_response(
                        request, ErrorCode.INVALID_REQUEST, "interrupt 已经恢复过。"
                    )
                )
            turn_id = str(values.get("turn_id") or "")
            trace_id = str(values.get("trace_id") or "")
            graph_finished = False
            try:
                await self._ensure_turn_started(
                    session_id=session_id,
                    request_id=request_id,
                    turn_id=turn_id,
                    trace_id=trace_id,
                )
                await self._append_audit_event(
                    session_id=session_id,
                    request_id=request_id,
                    turn_id=turn_id,
                    trace_id=trace_id,
                    event_type="agent_resumed",
                    sequence=len(values.get("node_events") or []),
                    payload={
                        "interrupt_id": active.interrupt_id,
                        "interrupt_kind": active.kind.value,
                    },
                )
                emitted_node_events = len(values.get("node_events") or [])
                node_attempts: dict[str, int] = {}
                raw_node_events = values.get("node_events")
                node_event_records: list[Any] = (
                    cast(list[Any], raw_node_events) if isinstance(raw_node_events, list) else []
                )
                for raw_record in node_event_records:
                    if not isinstance(raw_record, Mapping):
                        continue
                    record = cast(Mapping[str, Any], raw_record)
                    node_name = str(record.get("node_name") or "")
                    raw_attempt = record.get("retry_count")
                    attempt = raw_attempt if isinstance(raw_attempt, int) else 0
                    node_attempts[node_name] = max(node_attempts.get(node_name, 0), attempt + 1)
                async with asyncio.timeout(self._deps.settings.turn_timeout_seconds):
                    async for state in stream_values(
                        self._graph, Command[str](resume=resume.value), config
                    ):
                        values = dict(state)
                        emitted_node_events = await self._emit_snapshot_node_events(
                            values, emitted_node_events, node_attempts
                        )
                graph_finished = True
                interrupt = self._interrupt_of(values)
                if interrupt is not None:
                    await self._append_audit_event(
                        session_id=session_id,
                        request_id=request_id,
                        turn_id=turn_id,
                        trace_id=trace_id,
                        event_type="agent_interrupted",
                        sequence=len(cast(list[Any], values.get("node_events") or [])),
                        payload={
                            "interrupt_id": interrupt.interrupt_id,
                            "interrupt_kind": interrupt.kind.value,
                        },
                    )
                    return AgentTurnResult(interrupt=interrupt)
                response = self._response_of(values)
                if response is None:
                    response = self._bare_failed_response(
                        request, ErrorCode.INTERNAL_ERROR, "resume 未产出响应。"
                    ).model_copy(update={"turn_id": turn_id, "trace_id": trace_id})
                await self._ledger_save(session_id, response.request_id, response)
                await self._emit_terminal_event(response)
                return AgentTurnResult(response=response)
            except RequestLedgerUnavailableError:
                failed = self._bare_failed_response(
                    request,
                    ErrorCode.REQUEST_LEDGER_UNAVAILABLE,
                    "请求结果账本不可用，请稍后重试。",
                ).model_copy(update={"turn_id": turn_id, "trace_id": trace_id})
                await self._emit_terminal_event(failed)
                return AgentTurnResult(response=failed)
            except TimeoutError:
                if not graph_finished:
                    try:
                        await self._deps.checkpoint.release_resume(session_id, active.interrupt_id)
                    except Exception:
                        self._metrics_inc("checkpoint_failure_total")
                failed = self._bare_failed_response(
                    request,
                    ErrorCode.TURN_TIMEOUT,
                    "处理超时，请稍后重试。",
                ).model_copy(update={"turn_id": turn_id, "trace_id": trace_id})
                try:
                    await self._ledger_save(session_id, request_id, failed)
                except RequestLedgerUnavailableError:
                    pass
                await self._emit_terminal_event(failed)
                return AgentTurnResult(response=failed)
            except asyncio.CancelledError:
                if not graph_finished:
                    try:
                        await self._deps.checkpoint.release_resume(session_id, active.interrupt_id)
                    except Exception:
                        self._metrics_inc("checkpoint_failure_total")
                raise
            except Exception as exc:
                if not graph_finished:
                    try:
                        await self._deps.checkpoint.release_resume(session_id, active.interrupt_id)
                    except Exception:
                        self._metrics_inc("checkpoint_failure_total")
                await self._emit_agent_failure_from_exception(values, exc)
                failed = self._bare_failed_response(
                    request, ErrorCode.INTERNAL_ERROR, "resume 处理失败。"
                ).model_copy(update={"turn_id": turn_id, "trace_id": trace_id})
                await self._emit_terminal_event(failed)
                return AgentTurnResult(response=failed)

    async def _run_multi_agent(
        self,
        request: AgentRequest,
        context: AgentExecutionContext,
    ) -> AgentResponse:
        """受控 Multi-Agent 模式入口；workflow 模式仍走原有 graph。"""
        cached = await self._ledger_get(request.session_id, request.request_id)
        if cached is not None:
            return cached
        async with self._session_lock(request.session_id):
            cached = await self._ledger_get(request.session_id, request.request_id)
            if cached is not None:
                return cached
            try:
                from shijiajing_agent.multi_agent.checkpoint import (
                    LangGraphMultiAgentCheckpoint,
                )
                from shijiajing_agent.multi_agent.supervisor import MultiAgentSupervisor

                shadow_mode = self._deps.settings.orchestration_mode == "multi_agent_shadow"
                multi_agent_checkpoint = (
                    LangGraphMultiAgentCheckpoint(self._deps.graph_checkpointer)
                    if self._deps.graph_checkpointer is not None and not shadow_mode
                    else None
                )

                async with asyncio.timeout(self._deps.settings.turn_timeout_seconds):
                    outcome = await MultiAgentSupervisor(
                        self._deps,
                        planner_port=self._deps.supervisor_planner,
                        checkpoint=multi_agent_checkpoint,
                    ).run(
                        request,
                        context=context,
                        pause_for_hitl=False,
                        shadow=shadow_mode,
                    )
                response = outcome.response
                if shadow_mode:
                    from shijiajing_agent.multi_agent.shadow import compare_responses

                    legacy_response = await self._run_legacy_shadow(request)
                    comparison = compare_responses(
                        f"{request.session_id}:{request.request_id}",
                        legacy_response,
                        response,
                    )
                    result_label = "match" if comparison.equivalent else "mismatch"
                    response = response.model_copy(
                        update={
                            "notices": [
                                *response.notices,
                                f"shadow_compare:{result_label}",
                            ]
                        }
                    )
                if not shadow_mode:
                    await self._ledger_save(request.session_id, request.request_id, response)
                return response
            except RequestLedgerUnavailableError:
                return self._bare_failed_response(
                    request,
                    ErrorCode.REQUEST_LEDGER_UNAVAILABLE,
                    "请求结果账本不可用，请稍后重试。",
                )
            except TimeoutError:
                return self._bare_failed_response(
                    request,
                    ErrorCode.TURN_TIMEOUT,
                    "处理超时，请稍后重试。",
                )
            except Exception:
                return self._bare_failed_response(
                    request,
                    ErrorCode.INTERNAL_ERROR,
                    "处理失败，请稍后重试。",
                )

    async def _run_legacy_shadow(self, request: AgentRequest) -> AgentResponse:
        """运行旧图的只读副本，隔离 Memory、缓存、账本和事件写入。"""
        shadow_settings = replace(
            self._deps.settings,
            orchestration_mode="workflow",
            memory_enabled=False,
            memory_recall_enabled=False,
            memory_commit_enabled=False,
            hitl_enabled=False,
        )
        shadow_deps = replace(
            self._deps,
            settings=shadow_settings,
            graph_checkpointer=None,
            request_ledger=None,
            memory=None,
            cache=None,
            event_store=None,
        )
        try:
            response, _ = await AgentFacade(shadow_deps)._run_once(request, None)
            return response
        except Exception:
            return self._bare_failed_response(
                request,
                ErrorCode.INTERNAL_ERROR,
                "旧 Workflow shadow 执行失败。",
            )

    async def _start_multi_agent(
        self,
        request: AgentRequest,
        context: AgentExecutionContext,
    ) -> AgentTurnResult:
        """受控路径的 native start；interrupt 时保留原 plan/task checkpoint。"""
        if context.memory_enabled and context.memory_owner_id is None:
            return AgentTurnResult(
                response=self._bare_failed_response(
                    request,
                    ErrorCode.INVALID_REQUEST,
                    "启用记忆时必须提供可信 memory_owner_id。",
                )
            )
        if self._deps.settings.hitl_enabled and self._deps.graph_checkpointer is None:
            return AgentTurnResult(
                response=self._bare_failed_response(
                    request,
                    ErrorCode.INVALID_REQUEST,
                    "Multi-Agent HITL resume 需要 native persistence。",
                )
            )
        async with self._session_lock(request.session_id):
            cached = await self._ledger_get(request.session_id, request.request_id)
            if cached is not None:
                return AgentTurnResult(response=cached)
            try:
                from shijiajing_agent.multi_agent.checkpoint import (
                    LangGraphMultiAgentCheckpoint,
                )
                from shijiajing_agent.multi_agent.supervisor import MultiAgentSupervisor

                checkpoint = (
                    LangGraphMultiAgentCheckpoint(self._deps.graph_checkpointer)
                    if self._deps.graph_checkpointer is not None
                    else None
                )
                async with asyncio.timeout(self._deps.settings.turn_timeout_seconds):
                    outcome = await MultiAgentSupervisor(
                        self._deps,
                        planner_port=self._deps.supervisor_planner,
                        checkpoint=checkpoint,
                    ).run(
                        request,
                        context=context,
                        pause_for_hitl=True,
                        shadow=self._deps.settings.orchestration_mode == "multi_agent_shadow",
                    )
                if outcome.interrupt is not None:
                    return AgentTurnResult(interrupt=outcome.interrupt)
                await self._ledger_save(request.session_id, request.request_id, outcome.response)
                return AgentTurnResult(response=outcome.response)
            except TimeoutError:
                return AgentTurnResult(
                    response=self._bare_failed_response(
                        request, ErrorCode.TURN_TIMEOUT, "处理超时，请稍后重试。"
                    )
                )
            except RequestLedgerUnavailableError:
                return AgentTurnResult(
                    response=self._bare_failed_response(
                        request,
                        ErrorCode.REQUEST_LEDGER_UNAVAILABLE,
                        "请求结果账本不可用，请稍后重试。",
                    )
                )
            except Exception:
                return AgentTurnResult(
                    response=self._bare_failed_response(
                        request, ErrorCode.INTERNAL_ERROR, "处理失败，请稍后重试。"
                    )
                )

    async def _resume_multi_agent(
        self,
        session_id: str,
        resume: AgentResume,
        context: AgentExecutionContext,
    ) -> AgentTurnResult:
        """受控路径 resume：复用已保存的 Supervisor plan/task。"""
        async with self._session_lock(session_id):
            try:
                from shijiajing_agent.multi_agent.checkpoint import (
                    LangGraphMultiAgentCheckpoint,
                )
                from shijiajing_agent.multi_agent.supervisor import MultiAgentSupervisor

                checkpoint = (
                    LangGraphMultiAgentCheckpoint(self._deps.graph_checkpointer)
                    if self._deps.graph_checkpointer is not None
                    else None
                )
                async with asyncio.timeout(self._deps.settings.turn_timeout_seconds):
                    outcome = await MultiAgentSupervisor(
                        self._deps,
                        planner_port=self._deps.supervisor_planner,
                        checkpoint=checkpoint,
                    ).resume(
                        session_id,
                        resume,
                        context,
                        shadow=self._deps.settings.orchestration_mode == "multi_agent_shadow",
                    )
                if outcome.interrupt is not None:
                    return outcome
                if outcome.response is not None:
                    await self._ledger_save(
                        outcome.response.session_id,
                        outcome.response.request_id,
                        outcome.response,
                    )
                return outcome
            except TimeoutError:
                request = AgentRequest.model_validate(
                    {"session_id": session_id, "request_id": "resume", "text": "resume"}
                )
                return AgentTurnResult(
                    response=self._bare_failed_response(
                        request, ErrorCode.TURN_TIMEOUT, "处理超时，请稍后重试。"
                    )
                )
            except Exception:
                request = AgentRequest.model_validate(
                    {"session_id": session_id, "request_id": "resume", "text": "resume"}
                )
                return AgentTurnResult(
                    response=self._bare_failed_response(
                        request, ErrorCode.INTERNAL_ERROR, "resume 处理失败。"
                    )
                )

    async def _ledger_get(self, session_id: str, request_id: str) -> AgentResponse | None:
        if self._deps.request_ledger is None:
            return None
        try:
            return await self._deps.request_ledger.get_response(session_id, request_id)
        except RequestLedgerUnavailableError:
            raise
        except Exception as exc:
            raise RequestLedgerUnavailableError(str(exc)) from exc

    async def _ledger_save(self, session_id: str, request_id: str, response: AgentResponse) -> None:
        if self._deps.request_ledger is None:
            return
        started = time.monotonic()
        try:
            await self._deps.request_ledger.save_response(session_id, request_id, response)
        except SessionConflictError:
            raise
        except Exception as exc:
            if isinstance(exc, RequestLedgerUnavailableError):
                raise
            raise RequestLedgerUnavailableError(str(exc)) from exc
        await self._emit_component_event(
            session_id=session_id,
            request_id=request_id,
            turn_id=response.turn_id,
            trace_id=response.trace_id,
            node_name="request_ledger",
            duration_ms=round((time.monotonic() - started) * 1000.0, 2),
        )
        if self._deps.event_store is not None:
            try:
                await self._deps.event_store.append(
                    AgentEventRecord(
                        event_id=stable_event_id(
                            session_id,
                            request_id,
                            response.turn_id,
                            "supervisor",
                            None,
                            "request_result_committed",
                            0,
                        ),
                        session_id=session_id,
                        request_id=request_id,
                        turn_id=response.turn_id,
                        trace_id=response.trace_id,
                        agent_name="supervisor",
                        event_type="request_result_committed",
                        status=response.status.value,
                        output_hash=content_hash(response.model_dump(mode="json")),
                        payload={"response_hash": content_hash(response.model_dump(mode="json"))},
                        occurred_at=now_iso(),
                    )
                )
            except Exception:
                self._metrics_inc("event_store_failure_total")

    async def _record_ledger_repair(self, response: AgentResponse) -> None:
        """记录从 native checkpoint 补写 Request Ledger 的独立证据。"""
        self._metrics_inc("request_ledger_repair_total")
        if self._deps.event_store is None:
            return
        response_hash = content_hash(response.model_dump(mode="json"))
        try:
            await self._deps.event_store.append(
                AgentEventRecord(
                    event_id=stable_event_id(
                        response.session_id,
                        response.request_id,
                        response.turn_id,
                        "supervisor",
                        "request_ledger",
                        "request_ledger_repaired",
                        0,
                    ),
                    session_id=response.session_id,
                    request_id=response.request_id,
                    turn_id=response.turn_id,
                    trace_id=response.trace_id,
                    agent_name="supervisor",
                    node_name="request_ledger",
                    event_type="request_ledger_repaired",
                    status=response.status.value,
                    output_hash=response_hash,
                    payload={
                        "response_hash": response_hash,
                        "source": "native_checkpoint",
                    },
                    occurred_at=now_iso(),
                )
            )
        except Exception:
            self._metrics_inc("event_store_failure_total")

    async def _append_audit_event(
        self,
        *,
        session_id: str,
        request_id: str,
        turn_id: str,
        trace_id: str,
        event_type: str,
        sequence: int,
        payload: dict[str, Any],
    ) -> None:
        """追加 Event Store 生命周期事件；事件失败不改变工作流结果。"""
        interrupt_kind = payload.get("interrupt_kind")
        await self._emit_component_event(
            session_id=session_id,
            request_id=request_id,
            turn_id=turn_id,
            trace_id=trace_id,
            node_name="interrupt",
            interrupt_kind=interrupt_kind if isinstance(interrupt_kind, str) else None,
        )
        if self._deps.event_store is None:
            return
        try:
            await self._deps.event_store.append(
                AgentEventRecord(
                    event_id=stable_event_id(
                        session_id,
                        request_id,
                        turn_id,
                        "supervisor",
                        None,
                        event_type,
                        sequence,
                    ),
                    session_id=session_id,
                    request_id=request_id,
                    turn_id=turn_id,
                    trace_id=trace_id,
                    agent_name="supervisor",
                    node_name=None,
                    event_type=event_type,
                    payload=payload,
                    occurred_at=now_iso(),
                )
            )
        except Exception:
            self._metrics_inc("event_store_failure_total")

    @staticmethod
    def _interrupt_of(state: Mapping[str, Any]) -> AgentInterrupt | None:
        value = state.get("active_interrupt")
        if isinstance(value, AgentInterrupt):
            return value
        if isinstance(value, dict):
            try:
                return AgentInterrupt.model_validate(value)
            except Exception:
                pass
        raw_interrupts = state.get("__interrupt__")
        if isinstance(raw_interrupts, tuple):
            for item in cast(tuple[Any, ...], raw_interrupts):
                payload = getattr(item, "value", None)
                if isinstance(payload, dict):
                    try:
                        return AgentInterrupt.model_validate(payload)
                    except Exception:
                        continue
        return None

    @staticmethod
    def _interrupt_from_snapshot(snapshot: Any) -> AgentInterrupt | None:
        interrupts = getattr(snapshot, "interrupts", ())
        for item in interrupts or ():
            payload = getattr(item, "value", None)
            if isinstance(payload, dict):
                try:
                    return AgentInterrupt.model_validate(payload)
                except Exception:
                    continue
        return None

    # ------------------------------------------------------------------
    async def _run_once(
        self, request: AgentRequest, prev: AgentState | None
    ) -> tuple[AgentResponse, AgentState]:
        settings = self._deps.settings
        session_id = request.session_id
        trace_id = f"tr:{uuid.uuid4().hex[:16]}"
        turn_id = f"t:{uuid.uuid4().hex[:12]}"

        state = make_initial_state(request, prev)
        state["trace_id"] = trace_id
        state["turn_id"] = turn_id
        await self._ensure_turn_started(
            session_id=session_id,
            request_id=request.request_id,
            turn_id=turn_id,
            trace_id=trace_id,
        )

        expected_version: int | None = prev.get("state_version") if prev else None
        last_state: AgentState = state
        step_count = 0
        emitted_node_events = 0
        node_attempts: dict[str, int] = {}

        try:
            async for snapshot in stream_values(self._graph, cast(NativeTurnInput, state), None):
                # stream_mode="values" 首个快照是输入本身，不计步
                if not snapshot.get("node_events"):
                    continue
                step_count += 1
                if step_count > settings.max_workflow_steps:
                    raise WorkflowStepLimitError(f"超过最大步数 {settings.max_workflow_steps}")
                last_state = snapshot
                node_events = list(snapshot.get("node_events") or [])
                emit_node_events = bool(
                    self._deps.event_store is not None
                    or getattr(settings, "trace_backend", "structlog") == "opentelemetry"
                )
                if emit_node_events:
                    emitted_node_events = await self._emit_snapshot_node_events(
                        snapshot, emitted_node_events, node_attempts
                    )
                else:
                    emitted_node_events = len(node_events)
                expected_version = await self._checkpoint_save(
                    session_id, snapshot, expected_version
                )
        except SessionConflictError:
            raise
        except TimeoutError:
            raise  # 由 run() 统一转为 TURN_TIMEOUT
        except WorkflowStepLimitError:
            last_state = self._attach_failed_response(
                last_state,
                request,
                ErrorCode.WORKFLOW_STEP_LIMIT,
                "处理步骤超过上限，请简化查询后重试。",
            )
            await self._save_best_effort(session_id, last_state, expected_version)
        except CheckpointUnavailableError:
            last_state = self._attach_failed_response(
                last_state,
                request,
                ErrorCode.CHECKPOINT_UNAVAILABLE,
                "状态存储不可用，请稍后重试。",
            )
            await self._save_best_effort(session_id, last_state, expected_version)
        except Exception as exc:
            await self._emit_agent_failure_from_exception(last_state, exc)
            last_state = self._attach_failed_response(
                last_state, request, ErrorCode.INTERNAL_ERROR, "处理失败，请稍后重试。"
            )
            await self._save_best_effort(session_id, last_state, expected_version)

        response = self._response_of(last_state)
        if response is None:
            last_state = self._attach_failed_response(
                last_state,
                request,
                ErrorCode.INTERNAL_ERROR,
                "处理失败，请稍后重试。",
            )
            response = self._response_of(last_state)
        if response is None:
            response = self._bare_failed_response(
                request, ErrorCode.INTERNAL_ERROR, "处理失败，请稍后重试。"
            )
        await self._emit_terminal_event(response)
        self._metrics_inc("agent_turn_total", {"status": response.status.value})
        return response, last_state

    # ------------------------------------------------------------------
    def _attach_failed_response(
        self, state: AgentState, request: AgentRequest, code: ErrorCode, message: str
    ) -> AgentState:
        errors = list(state.get("errors") or [])
        if not any(e.get("error_code") == code.value for e in errors):
            errors.append({"node_name": "facade", "error_code": code.value, "message": message})
        response = AgentResponse(
            session_id=request.session_id,
            request_id=request.request_id,
            turn_id=str(state.get("turn_id", "")),
            status=AgentStatus.FAILED,
            message=message,
            recognition=state.get("recognition"),
            effective_constraints=state.get("effective_constraints"),
            notices=state.get("notices") or [],
            trace_id=str(state.get("trace_id", "")),
        )
        state["response"] = response
        state["errors"] = errors
        state["completion_reason"] = CompletionReason.FAILED
        recent_turns = list(state.get("recent_turns") or [])
        current_turn_id = str(state.get("turn_id", ""))
        last_summary = recent_turns[-1] if recent_turns else None
        if isinstance(last_summary, Mapping):
            last_summary_mapping = cast(Mapping[str, Any], last_summary)
            last_request_id = cast(str | None, last_summary_mapping.get("request_id"))
            last_turn_id = cast(str | None, last_summary_mapping.get("turn_id"))
        else:
            last_request_id = cast(str | None, getattr(last_summary, "request_id", None))
            last_turn_id = cast(str | None, getattr(last_summary, "turn_id", None))
        if last_request_id != request.request_id or last_turn_id != current_turn_id:
            summary_delta = append_turn_summary_node(
                state,
                recent_turns_limit=self._deps.settings.recent_turns_limit,
                recent_turns_max_bytes=self._deps.settings.recent_turns_max_bytes,
            )
            state["recent_turns"] = summary_delta["recent_turns"]
        return state

    async def _persist_native_failed_state(
        self,
        config: RunnableConfig,
        last_state: Mapping[str, Any],
        request: AgentRequest,
        response: AgentResponse,
        code: ErrorCode,
        message: str,
    ) -> None:
        """把 native 图异常转换为可恢复的 FAILED checkpoint。"""
        failure_state: dict[str, Any] = dict(last_state)
        failure_state.setdefault("current_request", request)
        errors = list(failure_state.get("errors") or [])
        errors.append({"node_name": "native_facade", "error_code": code.value, "message": message})
        failure_state["response"] = response
        failure_state["errors"] = errors
        failure_state["completion_reason"] = CompletionReason.FAILED
        recent_turns = list(failure_state.get("recent_turns") or [])
        last_summary = recent_turns[-1] if recent_turns else None
        if isinstance(last_summary, Mapping):
            last_summary_mapping = cast(Mapping[str, Any], last_summary)
            same_turn = (
                last_summary_mapping.get("request_id") == request.request_id
                and last_summary_mapping.get("turn_id") == response.turn_id
            )
        else:
            same_turn = bool(
                last_summary is not None
                and getattr(last_summary, "request_id", None) == request.request_id
                and getattr(last_summary, "turn_id", None) == response.turn_id
            )
        if same_turn:
            recent_turns_after = recent_turns
        else:
            summary_delta = append_turn_summary_node(
                cast(AgentState, failure_state),
                recent_turns_limit=self._deps.settings.recent_turns_limit,
                recent_turns_max_bytes=self._deps.settings.recent_turns_max_bytes,
            )
            recent_turns_after = summary_delta["recent_turns"]
        delta = {
            "response": response,
            "errors": errors,
            "completion_reason": CompletionReason.FAILED,
            "recent_turns": recent_turns_after,
        }
        try:
            await self._graph.aupdate_state(config, delta, as_node="append_turn_summary")
        except Exception:
            # checkpoint 不可用时仍返回已构造的失败响应；调用方会保留外部错误事件。
            return

    def _bare_failed_response(
        self, request: AgentRequest, code: ErrorCode, message: str
    ) -> AgentResponse:
        """无状态可挂载时的失败响应（checkpoint 不可用 / 冲突 / 整轮超时）。"""
        self._metrics_inc("agent_turn_total", {"status": AgentStatus.FAILED.value})
        return AgentResponse(
            session_id=request.session_id,
            request_id=request.request_id,
            turn_id="t:unknown",
            status=AgentStatus.FAILED,
            message=message,
            notices=[],
            trace_id="tr:unknown",
        )

    @staticmethod
    def _response_of(state: Mapping[str, Any]) -> AgentResponse | None:
        response = state.get("response")
        if isinstance(response, AgentResponse):
            return response
        if isinstance(response, dict):
            try:
                return AgentResponse.model_validate(response)
            except Exception:
                return None
        return None

    # ------------------------------------------------------------------
    async def _load_cached(self, session_id: str, request_id: str) -> AgentResponse | None:
        try:
            loaded = await self._checkpoint_load(session_id)
        except CheckpointUnavailableError:
            return None
        if loaded is None:
            return None
        response = loaded.get("response")
        if response is not None and response.request_id == request_id:
            return response
        return None

    async def _checkpoint_load(self, session_id: str) -> AgentState | None:
        last_exc: Exception | None = None
        for attempt in range(_CHECKPOINT_RETRIES):
            try:
                loaded = await self._deps.checkpoint.load(session_id)
                if loaded is None:
                    return None
                state, _ = loaded
                return state
            except SessionConflictError:
                raise
            except Exception as exc:
                last_exc = exc
                if attempt + 1 < _CHECKPOINT_RETRIES:
                    await asyncio.sleep(0.05 * (attempt + 1))
        raise CheckpointUnavailableError(f"checkpoint load 失败: {last_exc}") from last_exc

    async def _checkpoint_save(
        self, session_id: str, state: AgentState, expected_version: int | None
    ) -> int:
        last_exc: Exception | None = None
        started = time.monotonic()
        for attempt in range(_CHECKPOINT_RETRIES):
            try:
                saved_version = await self._deps.checkpoint.save(
                    session_id, state, expected_version
                )
                await self._emit_component_event(
                    session_id=session_id,
                    request_id=str(state.get("request_id") or ""),
                    turn_id=str(state.get("turn_id") or ""),
                    trace_id=str(state.get("trace_id") or ""),
                    node_name="checkpoint",
                    duration_ms=round((time.monotonic() - started) * 1000.0, 2),
                    retry_count=saved_version,
                )
                return saved_version
            except SessionConflictError:
                raise
            except Exception as exc:
                last_exc = exc
                if attempt + 1 < _CHECKPOINT_RETRIES:
                    await asyncio.sleep(0.05 * (attempt + 1))
        raise CheckpointUnavailableError(f"checkpoint save 失败: {last_exc}") from last_exc

    async def _save_best_effort(
        self, session_id: str, state: AgentState, expected_version: int | None
    ) -> None:
        """失败状态下尽力保存，保留 Checkpoint 与 trace。"""
        try:
            await self._checkpoint_save(session_id, state, expected_version)
        except (CheckpointUnavailableError, SessionConflictError):
            pass

    def _metrics_inc(
        self, name: str, labels: dict[str, str] | None = None, value: float = 1.0
    ) -> None:
        """指标输出失败不阻断业务（§20）。"""
        try:
            self._deps.metrics.inc(name, labels=labels, value=value)
        except Exception:
            pass

    async def _ensure_turn_started(
        self, *, session_id: str, request_id: str, turn_id: str, trace_id: str
    ) -> None:
        """为 legacy/native/resume 共用同一条 turn 根事件。"""
        key = (session_id, turn_id)
        if key in self._trace_started_turns:
            return
        await self._emit(
            AgentEvent(
                session_id=session_id,
                request_id=request_id,
                turn_id=turn_id,
                trace_id=trace_id,
                event_type=EventType.TURN_STARTED,
                timestamp=now_iso(),
            )
        )
        self._trace_started_turns.add(key)

    async def _emit_snapshot_node_events(
        self,
        snapshot: Mapping[str, Any],
        emitted_node_events: int,
        node_attempts: dict[str, int],
    ) -> int:
        """只投影本次 snapshot 新增的节点事件，并为 replay 补齐稳定 attempt。"""
        node_events = list(snapshot.get("node_events") or [])
        if not (
            self._deps.event_store is not None
            or getattr(self._deps.settings, "trace_backend", "structlog") == "opentelemetry"
        ):
            return len(node_events)
        for record in node_events[emitted_node_events:]:
            node_name = str(record.get("node_name") or "")
            raw_attempt = record.get("retry_count")
            if isinstance(raw_attempt, int):
                attempt = raw_attempt
                node_attempts[node_name] = max(node_attempts.get(node_name, 0), attempt + 1)
            else:
                attempt = node_attempts.get(node_name, 0)
                node_attempts[node_name] = attempt + 1
            enriched_record = dict(record)
            enriched_record.setdefault("retry_count", attempt)
            self._enrich_node_event(enriched_record, snapshot)
            agent_name = _AGENT_NAMES.get(node_name)
            if agent_name is not None:
                await self._emit_agent_lifecycle_event(
                    snapshot,
                    agent_name=agent_name,
                    event_type="agent_started",
                    node_name=node_name,
                    status=None,
                    payload={"entry_node": node_name},
                )
            await self._emit(self._agent_event_from_node_record(enriched_record))
            record_status = str(record.get("status") or "")
            if agent_name is not None and record_status == "failed":
                await self._emit_agent_lifecycle_event(
                    snapshot,
                    agent_name=agent_name,
                    event_type="agent_failed",
                    node_name=node_name,
                    status=NodeStatus.FAILED,
                    payload={
                        "failed_node": node_name,
                        "error_code": record.get("error_code") or "INTERNAL_ERROR",
                    },
                )
            elif agent_name is not None and node_name in _AGENT_TERMINAL_NODES.get(
                agent_name, frozenset()
            ):
                await self._emit_agent_lifecycle_event(
                    snapshot,
                    agent_name=agent_name,
                    event_type="agent_completed",
                    node_name=node_name,
                    status=NodeStatus.SUCCESS,
                    payload={"terminal_node": node_name},
                )
        if self._deps.graph_checkpointer is not None and node_events:
            await self._emit_component_event(
                session_id=str(snapshot.get("session_id") or ""),
                request_id=str(snapshot.get("request_id") or ""),
                turn_id=str(snapshot.get("turn_id") or ""),
                trace_id=str(snapshot.get("trace_id") or ""),
                node_name="checkpoint",
                checkpoint_migration="native",
            )
        return len(node_events)

    async def _emit_agent_lifecycle_event(
        self,
        snapshot: Mapping[str, Any],
        *,
        agent_name: str,
        event_type: str,
        node_name: str,
        status: NodeStatus | None,
        payload: dict[str, Any],
    ) -> None:
        """持久化子 Agent 生命周期事件；稳定 event_id 保证 replay 幂等。"""
        event_store = self._deps.event_store
        if event_store is None:
            return
        session_id = str(snapshot.get("session_id") or "")
        request_id = str(snapshot.get("request_id") or "")
        turn_id = str(snapshot.get("turn_id") or "")
        key = (session_id, turn_id, agent_name, event_type)
        if key in self._agent_lifecycle_events:
            return
        try:
            await event_store.append(
                AgentEventRecord(
                    event_id=stable_event_id(
                        session_id,
                        request_id,
                        turn_id,
                        agent_name,
                        None,
                        event_type,
                        0,
                    ),
                    session_id=session_id,
                    request_id=request_id,
                    turn_id=turn_id,
                    trace_id=str(snapshot.get("trace_id") or ""),
                    agent_name=agent_name,
                    node_name=node_name,
                    event_type=event_type,
                    status=status.value if status is not None else None,
                    payload=payload,
                    occurred_at=now_iso(),
                )
            )
        except Exception:
            self._metrics_inc("event_store_failure_total")
            return
        self._agent_lifecycle_events.add(key)

    async def _emit_agent_failure_from_exception(
        self, snapshot: Mapping[str, Any], exc: Exception
    ) -> None:
        """节点异常未形成新 snapshot 时，补发对应子 Agent 的 failed 事件。"""
        node_name = getattr(exc, "node_name", None)
        if not isinstance(node_name, str):
            return
        agent_name = _AGENT_NAMES.get(node_name)
        if agent_name is None:
            return
        await self._emit_agent_lifecycle_event(
            snapshot,
            agent_name=agent_name,
            event_type="agent_started",
            node_name=node_name,
            status=None,
            payload={"entry_node": node_name},
        )
        await self._emit_agent_lifecycle_event(
            snapshot,
            agent_name=agent_name,
            event_type="agent_failed",
            node_name=node_name,
            status=NodeStatus.FAILED,
            payload={
                "failed_node": node_name,
                "error_code": getattr(exc, "code", None) or "INTERNAL_ERROR",
            },
        )

    def _enrich_node_event(self, record: dict[str, Any], snapshot: Mapping[str, Any]) -> None:
        """把已有配置/状态版本投影到节点事件，不写入业务文本。"""
        record.setdefault("taxonomy_version", self._deps.taxonomy.taxonomy_version)
        for name in ("retrieval_index_version", "fusion_version", "rerank_version"):
            value = snapshot.get(name)
            if value is not None:
                record.setdefault(name, value)
        node_name = str(record.get("node_name") or "")
        if node_name in {"prepare_memory_mutations", "commit_memory"}:
            record.setdefault(
                "memory_operation_count",
                len(snapshot.get("pending_memory_mutations") or []),
            )
        prompt_spec = _MODEL_PROMPTS.get(node_name)
        if prompt_spec is None:
            return
        prompt_name, model_field = prompt_spec
        record.setdefault("prompt_version", load_prompt(prompt_name)[0])
        model = getattr(self._deps.settings, model_field, None)
        if model is not None:
            record.setdefault("model", model)

    async def _emit_component_event(
        self,
        *,
        session_id: str,
        request_id: str,
        turn_id: str,
        trace_id: str,
        node_name: str,
        duration_ms: float | None = None,
        retry_count: int | None = None,
        status: NodeStatus = NodeStatus.SUCCESS,
        cache_hit: bool | None = None,
        interrupt_kind: str | None = None,
        memory_operation_count: int | None = None,
        checkpoint_migration: str | None = None,
    ) -> None:
        """只发 Trace 的 runtime component span，不伪造持久化业务事件。"""
        if getattr(self._deps.settings, "trace_backend", "structlog") != "opentelemetry":
            return
        await self._emit(
            AgentEvent(
                session_id=session_id,
                request_id=request_id,
                turn_id=turn_id,
                trace_id=trace_id,
                event_type=EventType.NODE_COMPLETED,
                timestamp=now_iso(),
                agent_name=_AGENT_NAMES.get(node_name, "supervisor"),
                node_name=node_name,
                status=status,
                duration_ms=duration_ms,
                retry_count=retry_count,
                cache_hit=cache_hit,
                interrupt_kind=interrupt_kind,
                memory_operation_count=memory_operation_count,
                checkpoint_migration=checkpoint_migration,
            ),
            persist=False,
        )

    async def _emit_terminal_event(self, response: AgentResponse) -> None:
        await self._emit(
            AgentEvent(
                session_id=response.session_id,
                request_id=response.request_id,
                turn_id=response.turn_id,
                trace_id=response.trace_id,
                event_type=(
                    EventType.RESULTS_READY
                    if response.status != AgentStatus.FAILED
                    else EventType.TURN_FAILED
                ),
                timestamp=now_iso(),
                status=(
                    NodeStatus.SUCCESS
                    if response.status != AgentStatus.FAILED
                    else NodeStatus.FAILED
                ),
            )
        )

    @staticmethod
    def _agent_event_from_node_record(record: Mapping[str, Any]) -> AgentEvent:
        raw_status = record.get("status")
        status: NodeStatus | None = None
        if isinstance(raw_status, str):
            try:
                status = NodeStatus(raw_status)
            except ValueError:
                status = None
        fallback_used = record.get("fallback_used")
        return AgentEvent(
            session_id=str(record.get("session_id") or ""),
            request_id=str(record.get("request_id") or ""),
            turn_id=str(record.get("turn_id") or ""),
            trace_id=str(record.get("trace_id") or ""),
            event_type=(EventType.NODE_FALLBACK if fallback_used else EventType.NODE_COMPLETED),
            timestamp=str(record.get("started_at") or now_iso()),
            node_name=str(record.get("node_name") or ""),
            agent_name=_AGENT_NAMES.get(str(record.get("node_name") or ""), "supervisor"),
            status=status,
            duration_ms=record.get("duration_ms"),
            provider=record.get("provider"),
            model=record.get("model"),
            prompt_version=record.get("prompt_version"),
            taxonomy_version=record.get("taxonomy_version"),
            retrieval_index_version=record.get("retrieval_index_version"),
            fusion_version=record.get("fusion_version"),
            rerank_version=record.get("rerank_version"),
            token_usage=record.get("token_usage"),
            cache_hit=record.get("cache_hit"),
            interrupt_kind=record.get("interrupt_kind"),
            memory_operation_count=record.get("memory_operation_count"),
            checkpoint_migration=record.get("checkpoint_migration"),
            input_hash=record.get("input_hash"),
            output_hash=record.get("output_hash"),
            retry_count=record.get("retry_count"),
            fallback_used=fallback_used,
            candidate_count_in=record.get("candidate_count_in"),
            candidate_count_out=record.get("candidate_count_out"),
            error_code=record.get("error_code"),
        )

    async def _emit(self, event: AgentEvent, *, persist: bool = True) -> None:
        """Trace sink 失败不阻断业务（§20），但必须增加本地错误计数。"""
        try:
            await self._deps.trace.emit(event)
        except Exception:
            self._metrics_inc("trace_sink_failure_total")
        if persist and self._deps.event_store is not None:
            try:
                persisted_event_type = {
                    EventType.TURN_STARTED: "agent_started",
                    EventType.RESULTS_READY: "agent_completed",
                    EventType.TURN_FAILED: "agent_failed",
                    EventType.NODE_COMPLETED: "node_completed",
                    EventType.NODE_FALLBACK: "node_fallback",
                }.get(event.event_type, event.event_type.value)
                await self._deps.event_store.append(
                    AgentEventRecord(
                        event_id=stable_event_id(
                            event.session_id,
                            event.request_id,
                            event.turn_id,
                            "supervisor",
                            event.node_name,
                            persisted_event_type,
                            event.retry_count or 0,
                        ),
                        session_id=event.session_id,
                        request_id=event.request_id,
                        turn_id=event.turn_id,
                        trace_id=event.trace_id,
                        agent_name="supervisor",
                        node_name=event.node_name,
                        event_type=persisted_event_type,
                        status=event.status.value if event.status is not None else None,
                        input_hash=event.input_hash,
                        output_hash=event.output_hash,
                        payload={
                            "fallback_used": event.fallback_used,
                            "retry_count": event.retry_count,
                            "candidate_count_in": event.candidate_count_in,
                            "candidate_count_out": event.candidate_count_out,
                            "prompt_version": event.prompt_version,
                            "taxonomy_version": event.taxonomy_version,
                            "retrieval_index_version": event.retrieval_index_version,
                            "fusion_version": event.fusion_version,
                            "rerank_version": event.rerank_version,
                            "token_usage": event.token_usage,
                        },
                        occurred_at=event.timestamp,
                    )
                )
            except Exception:
                self._metrics_inc("event_store_failure_total")

    def _session_lock(self, session_id: str) -> asyncio.Lock:
        """进程内串行锁（开发用）；生产使用数据库 advisory lock。"""
        lock = self._locks.get(session_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[session_id] = lock
        return lock
