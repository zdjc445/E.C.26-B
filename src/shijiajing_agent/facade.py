"""Agent 门面（方案 §17、§18）。

职责：
- ``request_id`` 全局幂等：重复请求返回已保存响应，不重复调用外部依赖（§17.2）。
- 同一 ``session_id`` 串行执行；Checkpoint 乐观版本检查，冲突整轮最多重放一次（§17.3）。
- 每个节点完成后保存 super-step 状态；进程中断后从最近成功点恢复（§17.1、§17.4）。
- 最大步数与整轮超时保护（§9.3、§18）：超限转为 FAILED 响应，保留 trace。
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from typing import Any

from shijiajing_agent.contracts import (
    AgentEvent,
    AgentRequest,
    AgentResponse,
    AgentStatus,
    CompletionReason,
    EventType,
    NodeStatus,
    now_iso,
)
from shijiajing_agent.domain.taxonomy import Taxonomy
from shijiajing_agent.errors import (
    CheckpointUnavailableError,
    ErrorCode,
    SessionConflictError,
    WorkflowStepLimitError,
)
from shijiajing_agent.graph import build_graph
from shijiajing_agent.nodes.input_nodes import make_initial_state
from shijiajing_agent.ports.checkpoint import CheckpointPort
from shijiajing_agent.ports.models import (
    ExplanationModelPort,
    IntentModelPort,
    QueryRewritePort,
    VisionModelPort,
)
from shijiajing_agent.ports.observability import MetricsPort, TraceSinkPort
from shijiajing_agent.ports.retrieval import ProductRetrievalPort
from shijiajing_agent.state import AgentState

_CHECKPOINT_RETRIES = 2


@dataclass
class AgentDependencies:
    """端口与运行参数容器。测试与生产共用同一装配入口。"""

    taxonomy: Taxonomy
    settings: Any
    vision: VisionModelPort
    intent: IntentModelPort
    query_rewrite: QueryRewritePort
    explanation: ExplanationModelPort
    retrieval: ProductRetrievalPort
    checkpoint: CheckpointPort
    trace: TraceSinkPort
    metrics: MetricsPort


class AgentFacade:
    def __init__(self, deps: AgentDependencies) -> None:
        self._deps = deps
        self._graph = build_graph(deps)
        self._locks: dict[str, asyncio.Lock] = {}

    # ------------------------------------------------------------------
    async def run(self, request: AgentRequest) -> AgentResponse:
        """执行一轮 Agent turn。幂等、串行、超时与步数保护都在这里。"""
        session_id = request.session_id
        settings = self._deps.settings

        # §17.2 幂等：进入会话锁前先查一次已保存响应
        cached = await self._load_cached(session_id, request.request_id)
        if cached is not None:
            return cached

        async with self._session_lock(session_id):
            # 持锁后再查一次：并发窗口内可能有其他任务已完成
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
                return response
            except SessionConflictError:
                # §17.3 乐观版本冲突：整轮最多重放一次
                try:
                    prev = await self._checkpoint_load(session_id)
                except CheckpointUnavailableError:
                    prev = None
                try:
                    async with asyncio.timeout(settings.turn_timeout_seconds):
                        response, _ = await self._run_once(request, prev)
                    return response
                except SessionConflictError:
                    return self._bare_failed_response(
                        request, ErrorCode.SESSION_CONFLICT, "会话状态冲突，请重试。"
                    )
            except TimeoutError:
                return self._bare_failed_response(
                    request, ErrorCode.TURN_TIMEOUT, "处理超时，请稍后重试。"
                )

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
        await self._emit(
            AgentEvent(
                session_id=session_id,
                request_id=request.request_id,
                turn_id=turn_id,
                trace_id=trace_id,
                event_type=EventType.TURN_STARTED,
                timestamp=now_iso(),
            )
        )

        expected_version: int | None = prev.get("state_version") if prev else None
        last_state: AgentState = state
        step_count = 0

        try:
            async for snapshot in self._graph.astream(state, {}, stream_mode="values"):
                # stream_mode="values" 首个快照是输入本身，不计步
                if not snapshot.get("node_events"):
                    continue
                step_count += 1
                if step_count > settings.max_workflow_steps:
                    raise WorkflowStepLimitError(f"超过最大步数 {settings.max_workflow_steps}")
                last_state = snapshot
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
        except Exception:
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
        await self._emit(
            AgentEvent(
                session_id=session_id,
                request_id=request.request_id,
                turn_id=turn_id,
                trace_id=trace_id,
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
        return state

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
    def _response_of(state: AgentState) -> AgentResponse | None:
        response = state.get("response")
        return response if isinstance(response, AgentResponse) else None

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
        for attempt in range(_CHECKPOINT_RETRIES):
            try:
                return await self._deps.checkpoint.save(session_id, state, expected_version)
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
        """失败状态下尽力保存（§17.4：保留 Checkpoint 与 trace）。"""
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

    async def _emit(self, event: AgentEvent) -> None:
        """Trace sink 失败不阻断业务（§20），但必须增加本地错误计数。"""
        try:
            await self._deps.trace.emit(event)
        except Exception:
            self._metrics_inc("trace_sink_failure_total")

    def _session_lock(self, session_id: str) -> asyncio.Lock:
        """进程内串行锁（开发用）；生产使用数据库 advisory lock（§17.3）。"""
        lock = self._locks.get(session_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[session_id] = lock
        return lock
