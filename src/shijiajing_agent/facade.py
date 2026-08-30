"""受控 Multi-Agent 的统一应用门面。

门面只负责请求幂等、会话串行、整轮超时与 Supervisor 生命周期；业务任务的计划、
派发、汇合和恢复全部由 :class:`MultiAgentSupervisor` 负责。
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

from langgraph.checkpoint.base import BaseCheckpointSaver

from shijiajing_agent.adapters.event_store import stable_event_id
from shijiajing_agent.config import Settings
from shijiajing_agent.contracts import (
    AgentEventRecord,
    AgentExecutionContext,
    AgentRequest,
    AgentResponse,
    AgentResume,
    AgentStatus,
    AgentTurnResult,
    content_hash,
    now_iso,
)
from shijiajing_agent.domain.taxonomy import Taxonomy
from shijiajing_agent.errors import ErrorCode, RequestLedgerUnavailableError, SessionConflictError
from shijiajing_agent.multi_agent.checkpoint import LangGraphMultiAgentCheckpoint
from shijiajing_agent.multi_agent.supervisor import MultiAgentSupervisor
from shijiajing_agent.ports.cache import VersionedCachePort
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


@dataclass
class AgentDependencies:
    """Supervisor 与 Specialist Agent 共用的端口容器。"""

    taxonomy: Taxonomy
    settings: Settings
    vision: VisionModelPort
    intent: IntentModelPort
    query_rewrite: QueryRewritePort
    explanation: ExplanationModelPort
    retrieval: ProductRetrievalPort
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
    """对外暴露 run/start/resume 的唯一 Multi-Agent 入口。"""

    def __init__(self, deps: AgentDependencies) -> None:
        self._deps = deps
        self._locks: dict[str, asyncio.Lock] = {}

    @property
    def dependencies(self) -> AgentDependencies:
        return self._deps

    async def run(self, request: AgentRequest) -> AgentResponse:
        """执行不暂停的一轮请求。"""
        try:
            cached = await self._ledger_get(request.session_id, request.request_id)
            if cached is not None:
                return cached
            async with self._session_lock(request.session_id):
                cached = await self._ledger_get(request.session_id, request.request_id)
                if cached is not None:
                    return cached
                async with asyncio.timeout(self._deps.settings.turn_timeout_seconds):
                    outcome = await self._supervisor().run(
                        request,
                        context=AgentExecutionContext(),
                        pause_for_hitl=False,
                    )
                await self._ledger_save(request, outcome.response)
                return outcome.response
        except RequestLedgerUnavailableError:
            return self._failed(
                request,
                ErrorCode.REQUEST_LEDGER_UNAVAILABLE,
                "请求结果账本不可用，请稍后重试。",
            )
        except TimeoutError:
            return self._failed(request, ErrorCode.TURN_TIMEOUT, "处理超时，请稍后重试。")
        except Exception:
            return self._failed(request, ErrorCode.INTERNAL_ERROR, "处理失败，请稍后重试。")

    async def start(
        self,
        request: AgentRequest,
        context: AgentExecutionContext,
    ) -> AgentTurnResult:
        """启动支持 HITL 暂停与恢复的一轮请求。"""
        if context.memory_enabled and context.memory_owner_id is None:
            return AgentTurnResult(
                response=self._failed(
                    request,
                    ErrorCode.INVALID_REQUEST,
                    "启用记忆时必须提供可信 memory_owner_id。",
                )
            )
        if self._deps.settings.hitl_enabled and self._deps.graph_checkpointer is None:
            return AgentTurnResult(
                response=self._failed(
                    request,
                    ErrorCode.INVALID_REQUEST,
                    "Multi-Agent HITL resume 需要持久化 Checkpoint。",
                )
            )
        try:
            async with self._session_lock(request.session_id):
                cached = await self._ledger_get(request.session_id, request.request_id)
                if cached is not None:
                    return AgentTurnResult(response=cached)
                async with asyncio.timeout(self._deps.settings.turn_timeout_seconds):
                    outcome = await self._supervisor().run(
                        request,
                        context=context,
                        pause_for_hitl=True,
                    )
                if outcome.interrupt is not None:
                    return AgentTurnResult(interrupt=outcome.interrupt)
                await self._ledger_save(request, outcome.response)
                return AgentTurnResult(response=outcome.response)
        except RequestLedgerUnavailableError:
            return AgentTurnResult(
                response=self._failed(
                    request,
                    ErrorCode.REQUEST_LEDGER_UNAVAILABLE,
                    "请求结果账本不可用，请稍后重试。",
                )
            )
        except TimeoutError:
            return AgentTurnResult(
                response=self._failed(request, ErrorCode.TURN_TIMEOUT, "处理超时，请稍后重试。")
            )
        except Exception:
            return AgentTurnResult(
                response=self._failed(request, ErrorCode.INTERNAL_ERROR, "处理失败，请稍后重试。")
            )

    async def resume(
        self,
        session_id: str,
        resume: AgentResume,
        context: AgentExecutionContext,
    ) -> AgentTurnResult:
        """从 Supervisor Checkpoint 恢复一次 HITL 中断。"""
        request = AgentRequest(session_id=session_id, request_id="resume", text="resume")
        if self._deps.graph_checkpointer is None:
            return AgentTurnResult(
                response=self._failed(
                    request,
                    ErrorCode.INVALID_REQUEST,
                    "Multi-Agent resume 需要持久化 Checkpoint。",
                )
            )
        try:
            async with self._session_lock(session_id):
                async with asyncio.timeout(self._deps.settings.turn_timeout_seconds):
                    outcome = await self._supervisor().resume(session_id, resume, context)
                if outcome.response is not None:
                    completed_request = AgentRequest(
                        session_id=outcome.response.session_id,
                        request_id=outcome.response.request_id,
                        text="resume",
                    )
                    await self._ledger_save(completed_request, outcome.response)
                return outcome
        except RequestLedgerUnavailableError:
            return AgentTurnResult(
                response=self._failed(
                    request,
                    ErrorCode.REQUEST_LEDGER_UNAVAILABLE,
                    "请求结果账本不可用，请稍后重试。",
                )
            )
        except TimeoutError:
            return AgentTurnResult(
                response=self._failed(request, ErrorCode.TURN_TIMEOUT, "处理超时，请稍后重试。")
            )
        except Exception:
            return AgentTurnResult(
                response=self._failed(request, ErrorCode.INTERNAL_ERROR, "resume 处理失败。")
            )

    def _supervisor(self) -> MultiAgentSupervisor:
        checkpoint = (
            LangGraphMultiAgentCheckpoint(self._deps.graph_checkpointer)
            if self._deps.graph_checkpointer is not None
            else None
        )
        return MultiAgentSupervisor(
            self._deps,
            planner_port=self._deps.supervisor_planner,
            checkpoint=checkpoint,
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

    async def _ledger_save(self, request: AgentRequest, response: AgentResponse) -> None:
        if self._deps.request_ledger is None:
            return
        started = time.monotonic()
        try:
            await self._deps.request_ledger.save_response(
                request.session_id,
                request.request_id,
                response,
            )
        except SessionConflictError:
            raise
        except Exception as exc:
            if isinstance(exc, RequestLedgerUnavailableError):
                raise
            raise RequestLedgerUnavailableError(str(exc)) from exc
        self._observe("request_ledger_duration_ms", (time.monotonic() - started) * 1000)
        if self._deps.event_store is None:
            return
        response_hash = content_hash(response.model_dump(mode="json"))
        try:
            await self._deps.event_store.append(
                AgentEventRecord(
                    event_id=stable_event_id(
                        request.session_id,
                        request.request_id,
                        response.turn_id,
                        "supervisor",
                        None,
                        "request_result_committed",
                        0,
                    ),
                    session_id=request.session_id,
                    request_id=request.request_id,
                    turn_id=response.turn_id,
                    trace_id=response.trace_id,
                    agent_name="supervisor",
                    event_type="request_result_committed",
                    status=response.status.value,
                    output_hash=response_hash,
                    payload={"response_hash": response_hash},
                    occurred_at=now_iso(),
                )
            )
        except Exception:
            self._increment("event_store_failure_total")

    def _failed(self, request: AgentRequest, code: ErrorCode, message: str) -> AgentResponse:
        self._increment(
            "agent_turn_total",
            {"status": AgentStatus.FAILED.value, "error_code": code.value},
        )
        return AgentResponse(
            session_id=request.session_id,
            request_id=request.request_id,
            turn_id="t:unknown",
            status=AgentStatus.FAILED,
            message=message,
            trace_id="tr:unknown",
        )

    def _increment(self, name: str, labels: dict[str, str] | None = None) -> None:
        try:
            self._deps.metrics.inc(name, labels=labels)
        except Exception:
            return

    def _observe(self, name: str, value: float) -> None:
        try:
            self._deps.metrics.observe(name, value)
        except Exception:
            return

    def _session_lock(self, session_id: str) -> asyncio.Lock:
        lock = self._locks.get(session_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[session_id] = lock
        return lock
