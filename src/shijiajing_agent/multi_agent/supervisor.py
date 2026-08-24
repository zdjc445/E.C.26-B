"""受控层级式 Supervisor 执行器。

它只负责计划、barrier、结果归并、规范约束和副作用授权。五个 Specialist 通过 registry
接收最小任务输入，结果统一以 ``AgentResultV2`` 返回。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from time import perf_counter
from typing import Any, cast

from langgraph.types import Command

from shijiajing_agent.contracts import (
    AgentExecutionContext,
    AgentInterrupt,
    AgentRequest,
    AgentResponse,
    AgentResultV2,
    AgentResume,
    AgentStatus,
    AgentTaskKind,
    AgentTaskV2,
    AgentTurnResult,
    CanonicalUnderstanding,
    ClarificationResume,
    ExecutionPlan,
    ExecutionPlanPatch,
    ExplanationTaskInput,
    ExplanationTaskOutput,
    IntentTaskInput,
    IntentTaskOutput,
    InterruptKind,
    MemoryConfirmationResume,
    MemoryRecord,
    MemoryTaskInput,
    MemoryTaskOutput,
    NodeStatus,
    RecognitionReviewResume,
    RecognitionTaskInput,
    RecognitionTaskOutput,
    RetrievalTaskInput,
    RetrievalTaskOutput,
    SameItemReviewResume,
    SupervisorBudgetUsage,
    SupervisorPlanningInput,
    SupervisorReplanningInput,
    TaskRecord,
)
from shijiajing_agent.domain.constraints import ClarificationBuilder, ConstraintMerger
from shijiajing_agent.domain.memory_policy import apply_memory_defaults
from shijiajing_agent.errors import PlanValidationError
from shijiajing_agent.multi_agent.agents.base import result_for
from shijiajing_agent.multi_agent.checkpoint import (
    MultiAgentCheckpointPort,
    agent_task_checkpoint_namespace,
    supervisor_checkpoint_namespace,
)
from shijiajing_agent.multi_agent.dispatcher import dispatch_tasks_with_send
from shijiajing_agent.multi_agent.planner import (
    DeterministicPlanner,
    GuardedSupervisorPlanner,
    PlanValidator,
    apply_plan_patch,
)
from shijiajing_agent.multi_agent.registry import SpecialistAgentRegistry, build_registry
from shijiajing_agent.state import SupervisorState, merge_task_results


@dataclass(frozen=True)
class SupervisorRunResult:
    state: SupervisorState
    response: AgentResponse
    plan: ExecutionPlan
    interrupt: AgentInterrupt | None = None


class MultiAgentSupervisor:
    """运行一个受控计划；同一 Supervisor 实例不持有 Specialist 私有状态。"""

    def __init__(
        self,
        deps: Any,
        *,
        registry: SpecialistAgentRegistry | None = None,
        planner: DeterministicPlanner | None = None,
        planner_port: Any | None = None,
        checkpoint: MultiAgentCheckpointPort | None = None,
    ) -> None:
        self._deps = deps
        self._registry = registry or build_registry(deps)
        self._planner = planner or DeterministicPlanner(
            max_tasks=getattr(deps.settings, "max_agent_tasks", 32),
            max_replans=getattr(deps.settings, "max_supervisor_replans", 2),
        )
        self._planner_port = GuardedSupervisorPlanner(
            self._planner,
            planner_port,
            mode=getattr(deps.settings, "supervisor_planner_mode", "off"),
        )
        self._checkpoint = checkpoint

    @property
    def registry(self) -> SpecialistAgentRegistry:
        return self._registry

    def create_plan(
        self,
        request: AgentRequest,
        *,
        context: AgentExecutionContext | None = None,
    ) -> ExecutionPlan:
        return self._planner.create_plan(
            request,
            context=context,
            taxonomy_version=self._deps.taxonomy.taxonomy_version,
        )

    async def run(
        self,
        request: AgentRequest,
        *,
        context: AgentExecutionContext | None = None,
        shadow: bool = False,
        pause_for_hitl: bool | None = None,
        resume: AgentResume | None = None,
    ) -> SupervisorRunResult:
        context = context or AgentExecutionContext()
        pause_for_hitl = (
            bool(getattr(self._deps.settings, "hitl_enabled", False))
            if pause_for_hitl is None
            else pause_for_hitl
        )
        baseline_plan = self._planner.create_plan(
            request,
            context=context,
            taxonomy_version=self._deps.taxonomy.taxonomy_version,
        )
        plan = baseline_plan
        planning_outcome = None
        started = perf_counter()
        task_records = {task.task_id: TaskRecord(task=task) for task in plan.tasks}
        state: dict[str, Any] = {
            "schema_version": "2.0",
            "session_id": request.session_id,
            "request_id": request.request_id,
            "turn_id": f"turn:{request.request_id}",
            "trace_id": f"trace:{request.request_id}",
            "current_request": request,
            "execution_context": context,
            "plan": plan,
            "planning_outcome": planning_outcome,
            "task_records": task_records,
            "task_results": {},
            "canonical_understanding": CanonicalUnderstanding(),
            "replan_count": 0,
            "total_task_count": 0,
            "budget_usage": SupervisorBudgetUsage(),
            "notices": [],
            "events": [],
            "hitl_completed": [],
            "resume_history": [],
            "memory_authorized": not bool(getattr(self._deps.settings, "hitl_enabled", False)),
        }
        checkpoint_namespace = supervisor_checkpoint_namespace(
            request.session_id, str(state["turn_id"]), plan.plan_id
        )
        checkpoint_version: int | None = None
        if self._checkpoint is not None:
            saved = await self._checkpoint.load_supervisor(checkpoint_namespace)
            if saved is not None:
                state = dict(saved[0])
                checkpoint_version = saved[1]
                restored_plan = state.get("plan")
                if isinstance(restored_plan, ExecutionPlan):
                    plan = restored_plan
                task_records = dict(state.get("task_records") or task_records)
        if self._checkpoint is None or checkpoint_version is None:
            plan = await self._planner_port.create_plan(
                SupervisorPlanningInput(
                    request=request,
                    execution_context=context,
                    taxonomy_version=self._deps.taxonomy.taxonomy_version,
                )
            )
            planning_outcome = self._planner_port.last_outcome
            state["plan"] = plan
            state["planning_outcome"] = planning_outcome
        else:
            restored_outcome = state.get("planning_outcome")
            planning_outcome = (
                restored_outcome
                if restored_outcome is None or hasattr(restored_outcome, "plan_hash")
                else None
            )
        plan = PlanValidator().validate(plan)
        results: dict[str, AgentResultV2] = dict(state.get("task_results") or {})
        if self._checkpoint is not None:
            for task in plan.tasks:
                if task.task_id in results:
                    continue
                namespace = agent_task_checkpoint_namespace(
                    request.session_id,
                    str(state["turn_id"]),
                    plan.plan_id,
                    task.task_id,
                )
                restored_result = await self._checkpoint.load_task(namespace)
                if restored_result is not None:
                    results = merge_task_results(results, restored_result)
                    task_records[task.task_id] = task_records[task.task_id].model_copy(
                        update={
                            "status": restored_result.status,
                            "result_hash": restored_result.output_hash,
                        }
                    )

        active_interrupt = state.get("active_interrupt")
        if active_interrupt is not None and not isinstance(active_interrupt, AgentInterrupt):
            active_interrupt = AgentInterrupt.model_validate(active_interrupt)
            state["active_interrupt"] = active_interrupt
        if active_interrupt is not None and resume is None and pause_for_hitl:
            return SupervisorRunResult(
                state=cast(SupervisorState, state),
                response=self._interrupt_response(request, state, active_interrupt),
                plan=plan,
                interrupt=active_interrupt,
            )
        if resume is not None and active_interrupt is not None:
            resume = resume.model_copy(
                update={"value": dict(Command(resume=resume.value).resume or {})}
            )
            self._apply_resume(resume, plan, results, task_records, state, active_interrupt)
            plan = cast(ExecutionPlan, state["plan"])
        elif resume is not None and resume.interrupt_id in set(state.get("resume_history") or []):
            response = state.get("final_response") or self._build_response(request, state, results)
            if response is None:
                response = AgentResponse(
                    session_id=request.session_id,
                    request_id=request.request_id,
                    turn_id=str(state["turn_id"]),
                    status=AgentStatus.FAILED,
                    message="resume 已处理。",
                    trace_id=str(state["trace_id"]),
                )
            return SupervisorRunResult(
                state=cast(SupervisorState, state), response=response, plan=plan
            )

        while len(results) < len(plan.tasks):
            ready = [
                record.task
                for task_id, record in task_records.items()
                if task_id not in results
                and all(parent in results for parent in record.task.depends_on)
            ]
            if not ready:
                raise PlanValidationError("计划无法继续：存在未满足依赖或循环")

            dispatchable: list[AgentTaskV2] = []
            for task in ready:
                interrupt = self._maybe_interrupt(task, results, state, pause_for_hitl)
                if interrupt is not None:
                    state["active_interrupt"] = interrupt
                    state["task_results"] = results
                    if self._checkpoint is not None:
                        checkpoint_version = await self._checkpoint.save_supervisor(
                            checkpoint_namespace,
                            cast(SupervisorState, state),
                            checkpoint_version,
                        )
                    return SupervisorRunResult(
                        state=cast(SupervisorState, state),
                        response=self._interrupt_response(request, state, interrupt),
                        plan=plan,
                        interrupt=interrupt,
                    )
                if self._should_skip(task, results, state, shadow=shadow):
                    result = self._skip_result(task)
                    results = merge_task_results(results, result)
                    task_records[task.task_id] = task_records[task.task_id].model_copy(
                        update={"status": NodeStatus.SKIPPED, "result_hash": result.output_hash}
                    )
                    await self._save_task_checkpoint(request, plan, task, result, state)
                    continue
                dispatchable.append(self._prepare_task(task, results, state))

            if dispatchable:
                returned = await dispatch_tasks_with_send(self._registry, dispatchable)
                for task in dispatchable:
                    result = returned[task.task_id]
                    results = merge_task_results(results, result)
                    await self._save_task_checkpoint(request, plan, task, result, state)
                    task_records[task.task_id] = task_records[task.task_id].model_copy(
                        update={
                            "status": result.status,
                            "result_hash": result.output_hash,
                            "authorized": task.task_kind is AgentTaskKind.MEMORY_COMMIT,
                        }
                    )
                    state["total_task_count"] = int(state.get("total_task_count", 0)) + 1

            self._reconcile(results, state)
            plan = await self._maybe_replan(plan, results, task_records, state)
            state["plan"] = plan
            state["task_results"] = results
            if self._checkpoint is not None:
                checkpoint_version = await self._checkpoint.save_supervisor(
                    checkpoint_namespace,
                    cast(SupervisorState, state),
                    checkpoint_version,
                )
            response = (
                self._build_response(request, state, results)
                if all(task.task_id in results for task in plan.tasks)
                else None
            )
            if response is not None:
                state["final_response"] = response

        response = state.get("final_response") or self._build_response(request, state, results)
        if response is None:
            response = AgentResponse(
                session_id=request.session_id,
                request_id=request.request_id,
                turn_id=str(state["turn_id"]),
                status=AgentStatus.FAILED,
                message="处理失败，请稍后重试。",
                trace_id=str(state["trace_id"]),
            )
        if shadow:
            state["notices"] = [
                *list(state.get("notices") or []),
                "multi_agent_shadow：未提交 Memory 副作用",
            ]
            response = response.model_copy(update={"notices": list(state["notices"])})
        usage = state["budget_usage"].model_copy(
            update={
                "task_count": int(state.get("total_task_count", 0)),
                "elapsed_ms": (perf_counter() - started) * 1000,
            }
        )
        state["budget_usage"] = usage
        state["task_results"] = results
        return SupervisorRunResult(state=cast(SupervisorState, state), response=response, plan=plan)

    async def resume(
        self,
        session_id: str,
        resume: AgentResume,
        context: AgentExecutionContext,
        *,
        shadow: bool = False,
    ) -> AgentTurnResult:
        """从受控 Supervisor checkpoint 继续原 plan，不重新创建整轮请求。"""
        if self._checkpoint is None:
            request = AgentRequest.model_validate(
                {"session_id": session_id, "request_id": "resume", "text": "resume"}
            )
            return AgentTurnResult(
                response=AgentResponse(
                    session_id=session_id,
                    request_id="resume",
                    turn_id="resume",
                    status=AgentStatus.FAILED,
                    message="Multi-Agent native persistence 未启用，不能 resume。",
                    trace_id="resume",
                )
            )
        active = await self._checkpoint.load_active(session_id)
        if active is None:
            return AgentTurnResult(
                response=AgentResponse(
                    session_id=session_id,
                    request_id="resume",
                    turn_id="resume",
                    status=AgentStatus.FAILED,
                    message="当前 session 没有待恢复的 Multi-Agent interrupt。",
                    trace_id="resume",
                )
            )
        request = active[1].get("current_request")
        if not isinstance(request, AgentRequest):
            request = AgentRequest.model_validate(request)
        outcome = await self.run(
            request,
            context=context,
            shadow=shadow,
            pause_for_hitl=True,
            resume=resume,
        )
        if outcome.interrupt is not None:
            return AgentTurnResult(interrupt=outcome.interrupt)
        return AgentTurnResult(response=outcome.response)

    def _maybe_interrupt(
        self,
        task: AgentTaskV2,
        results: dict[str, AgentResultV2],
        state: dict[str, Any],
        pause_for_hitl: bool,
    ) -> AgentInterrupt | None:
        if not pause_for_hitl or not getattr(self._deps.settings, "hitl_enabled", False):
            return None
        if state.get("active_interrupt") is not None:
            return None
        completed = set(state.get("hitl_completed") or [])
        if task.task_kind is AgentTaskKind.RETRIEVE_AND_RANK:
            recognition = next(
                (
                    result.output
                    for result in reversed(list(results.values()))
                    if isinstance(result.output, RecognitionTaskOutput)
                    and result.output.review_recommended
                ),
                None,
            )
            if recognition is not None and "recognition_review" not in completed:
                return self._make_interrupt(
                    state,
                    InterruptKind.RECOGNITION_REVIEW,
                    "recognition_review",
                    "图片识别置信度较低，请确认或修正识别结果。",
                    {
                        "recognition": recognition.recognition.model_dump(mode="json")
                        if recognition.recognition is not None
                        else None
                    },
                )
            constraints = state["canonical_understanding"].constraints
            if (
                constraints is None or constraints.category_id.value is None
            ) and "clarification" not in completed:
                return self._make_interrupt(
                    state,
                    InterruptKind.CLARIFICATION,
                    "clarification",
                    "请补充商品品类后继续比价。",
                    {"missing_fields": ["category_id"]},
                )
        if task.task_kind is AgentTaskKind.EXPLAIN and "same_item_review" not in completed:
            retrieval = next(
                (
                    result.output
                    for result in reversed(list(results.values()))
                    if isinstance(result.output, RetrievalTaskOutput)
                ),
                None,
            )
            if retrieval is not None and retrieval.same_item_review_pairs:
                return self._make_interrupt(
                    state,
                    InterruptKind.SAME_ITEM_REVIEW,
                    "same_item_review",
                    "发现可能属于同一商品但证据不足的候选，请确认是否合并。",
                    {
                        "pairs": [
                            pair.model_dump(mode="json")
                            for pair in retrieval.same_item_review_pairs
                        ]
                    },
                )
        if task.task_kind is AgentTaskKind.MEMORY_COMMIT and "memory_confirmation" not in completed:
            prepare = next(
                (
                    result.output
                    for result in reversed(list(results.values()))
                    if isinstance(result.output, MemoryTaskOutput)
                    and result.output.operation == "prepare"
                ),
                None,
            )
            if prepare is not None and prepare.mutations:
                return self._make_interrupt(
                    state,
                    InterruptKind.MEMORY_CONFIRMATION,
                    "memory_confirmation",
                    "本轮请求包含长期偏好变更，是否保存？",
                    {"mutations": [item.model_dump(mode="json") for item in prepare.mutations]},
                )
        return None

    @staticmethod
    def _make_interrupt(
        state: dict[str, Any],
        kind: InterruptKind,
        stage: str,
        prompt: str,
        payload: dict[str, Any],
    ) -> AgentInterrupt:
        request = state["current_request"]
        generation = int(state.get("interrupt_generation", 0)) + 1
        raw = "|".join(
            (
                request.session_id,
                request.request_id,
                str(state["turn_id"]),
                kind.value,
                str(generation),
            )
        )
        interrupt_id = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        state["interrupt_generation"] = generation
        state["hitl_stage"] = stage
        return AgentInterrupt(
            interrupt_id=interrupt_id,
            session_id=request.session_id,
            request_id=request.request_id,
            turn_id=str(state["turn_id"]),
            trace_id=str(state["trace_id"]),
            kind=kind,
            prompt=prompt,
            payload={"stage": stage, "plan_id": state["plan"].plan_id, **payload},
        )

    @staticmethod
    def _interrupt_response(
        request: AgentRequest,
        state: dict[str, Any],
        interrupt: AgentInterrupt,
    ) -> AgentResponse:
        return AgentResponse(
            session_id=request.session_id,
            request_id=request.request_id,
            turn_id=str(state["turn_id"]),
            status=AgentStatus.CLARIFICATION,
            message=interrupt.prompt,
            recognition=state["canonical_understanding"].recognition,
            effective_constraints=state["canonical_understanding"].constraints,
            notices=list(state.get("notices") or []),
            trace_id=str(state["trace_id"]),
        )

    def _apply_resume(
        self,
        resume: AgentResume,
        plan: ExecutionPlan,
        results: dict[str, AgentResultV2],
        task_records: dict[str, TaskRecord],
        state: dict[str, Any],
        active: AgentInterrupt,
    ) -> None:
        history = list(state.get("resume_history") or [])
        if resume.interrupt_id != active.interrupt_id:
            raise ValueError("interrupt_id 不匹配")
        if resume.interrupt_id in history:
            return
        stage = str(state.get("hitl_stage") or active.payload.get("stage") or "")
        if stage == "clarification":
            answer = ClarificationResume.model_validate(resume.value)
            request = state["current_request"]
            if answer.action == "answer":
                updated_request = request.model_copy(update={"text": answer.text})
            else:
                updated_request = request.model_copy(
                    update={"selected_option_id": answer.option_id, "text": answer.option_id}
                )
            state["current_request"] = updated_request
            old = next(
                task
                for task in reversed(plan.tasks)
                if task.task_kind is AgentTaskKind.PARSE_INTENT
            )
            new = old.model_copy(
                update={
                    "task_id": f"{old.task_id}:resume:{old.attempt + 1}",
                    "parent_task_id": old.task_id,
                    "attempt": old.attempt + 1,
                    "idempotency_key": f"{old.idempotency_key}:resume:{old.attempt + 1}",
                    "input": IntentTaskInput(
                        text=updated_request.text,
                        selected_option_id=updated_request.selected_option_id,
                    ),
                }
            )
            plan = self._replace_task(plan, task_records, old.task_id, new)
        elif stage == "recognition_review":
            answer = RecognitionReviewResume.model_validate(resume.value)
            old_result = next(
                result
                for result in reversed(list(results.values()))
                if isinstance(result.output, RecognitionTaskOutput)
                and result.output.recognition is not None
            )
            recognition_output = old_result.output
            if (
                not isinstance(recognition_output, RecognitionTaskOutput)
                or recognition_output.recognition is None
            ):
                raise ValueError("识别结果 output 类型无效")
            old_task = next(task for task in plan.tasks if task.task_id == old_result.task_id)
            if answer.action == "reject":
                plan = self._remove_dependency(plan, task_records, old_task.task_id)
            elif answer.action == "edit":
                if answer.correction is None:
                    raise ValueError("识别修正缺少 correction")
                new = old_task.model_copy(
                    update={
                        "task_id": f"{old_task.task_id}:review:{old_task.attempt + 1}",
                        "parent_task_id": old_task.task_id,
                        "task_kind": AgentTaskKind.APPLY_CORRECTION,
                        "attempt": old_task.attempt + 1,
                        "idempotency_key": (
                            f"{old_task.idempotency_key}:review:{old_task.attempt + 1}"
                        ),
                        "input": RecognitionTaskInput(
                            correction=answer.correction,
                            previous_recognition=recognition_output.recognition,
                            taxonomy_version=self._deps.taxonomy.taxonomy_version,
                        ),
                    }
                )
                plan = self._replace_task(plan, task_records, old_task.task_id, new)
        elif stage == "same_item_review":
            answer = SameItemReviewResume.model_validate(resume.value)
            if answer.action == "split":
                ids = {
                    item
                    for pair in active.payload.get("pairs", [])
                    for item in (
                        str(pair.get("offer_a_id")),
                        str(pair.get("offer_b_id")),
                    )
                    if isinstance(pair, dict)
                }
                old = next(
                    task
                    for task in reversed(plan.tasks)
                    if task.task_kind is AgentTaskKind.RETRIEVE_AND_RANK
                )
                if not isinstance(old.input, RetrievalTaskInput):
                    raise ValueError("retrieval task input 无效")
                new = old.model_copy(
                    update={
                        "task_id": f"{old.task_id}:review:{old.attempt + 1}",
                        "parent_task_id": old.task_id,
                        "attempt": old.attempt + 1,
                        "idempotency_key": f"{old.idempotency_key}:review:{old.attempt + 1}",
                        "input": old.input.model_copy(
                            update={
                                "same_item_review_action": "split",
                                "same_item_review_offer_ids": sorted(ids),
                            }
                        ),
                    }
                )
                plan = self._replace_task(plan, task_records, old.task_id, new)
        elif stage == "memory_confirmation":
            answer = MemoryConfirmationResume.model_validate(resume.value)
            state["memory_authorized"] = answer.action == "approve"
        else:
            raise ValueError("未知 Multi-Agent interrupt stage")
        state["plan"] = plan
        state["active_interrupt"] = None
        state["hitl_stage"] = None
        if stage not in history:
            state["hitl_completed"] = [*list(state.get("hitl_completed") or []), stage]
        state["resume_history"] = [*history, resume.interrupt_id]

    @staticmethod
    def _replace_task(
        plan: ExecutionPlan,
        task_records: dict[str, TaskRecord],
        old_task_id: str,
        replacement: AgentTaskV2,
    ) -> ExecutionPlan:
        updated = apply_plan_patch(
            plan,
            ExecutionPlanPatch(
                add_tasks=[replacement],
                replace_task_ids={old_task_id: replacement.task_id},
            ),
        )
        for task in updated.tasks:
            current = task_records.get(task.task_id)
            task_records[task.task_id] = (
                current.model_copy(update={"task": task})
                if current is not None
                else TaskRecord(task=task)
            )
        return updated

    @staticmethod
    def _remove_dependency(
        plan: ExecutionPlan,
        task_records: dict[str, TaskRecord],
        removed_task_id: str,
    ) -> ExecutionPlan:
        updated = PlanValidator().validate(
            plan.model_copy(
                update={
                    "tasks": [
                        task.model_copy(
                            update={
                                "depends_on": [
                                    dependency
                                    for dependency in task.depends_on
                                    if dependency != removed_task_id
                                ]
                            }
                        )
                        for task in plan.tasks
                    ]
                }
            )
        )
        for task in updated.tasks:
            if task.task_id in task_records:
                task_records[task.task_id] = task_records[task.task_id].model_copy(
                    update={"task": task}
                )
        return updated

    async def _maybe_replan(
        self,
        plan: ExecutionPlan,
        results: dict[str, AgentResultV2],
        task_records: dict[str, TaskRecord],
        state: dict[str, Any],
    ) -> ExecutionPlan:
        if int(state.get("replan_count", 0)) >= plan.max_replans:
            return plan
        existing_ids = {candidate.task_id for candidate in plan.tasks}
        failed_task_ids: list[str] = []
        for task in plan.tasks:
            result = results.get(task.task_id)
            error = result.error if result is not None else None
            if (
                result is not None
                and result.status is NodeStatus.FAILED
                and error is not None
                and error.retryable
                and task.attempt <= task.budget.max_retries
                and task.task_kind is not AgentTaskKind.MEMORY_COMMIT
                and f"{task.task_id}:retry:{task.attempt + 1}" not in existing_ids
            ):
                failed_task_ids.append(task.task_id)
        if not failed_task_ids:
            return plan
        patch = await self._planner_port.revise_plan(
            SupervisorReplanningInput(
                plan=plan,
                task_results=results,
                failed_task_ids=failed_task_ids,
                reason_code="retryable_task_failure",
            )
        )
        updated = apply_plan_patch(plan, patch)
        for task in updated.tasks:
            current = task_records.get(task.task_id)
            if current is None:
                task_records[task.task_id] = TaskRecord(task=task)
            else:
                task_records[task.task_id] = current.model_copy(update={"task": task})
        state["replan_count"] = int(state.get("replan_count", 0)) + 1
        return updated

    async def _save_task_checkpoint(
        self,
        request: AgentRequest,
        plan: ExecutionPlan,
        task: AgentTaskV2,
        result: AgentResultV2,
        state: dict[str, Any],
    ) -> None:
        if self._checkpoint is None:
            return
        namespace = agent_task_checkpoint_namespace(
            request.session_id,
            str(state["turn_id"]),
            plan.plan_id,
            task.task_id,
        )
        await self._checkpoint.save_task(namespace, result)

    @staticmethod
    def _skip_result(task: AgentTaskV2) -> AgentResultV2:
        return result_for(
            task,
            status=NodeStatus.SKIPPED,
            error=None,
        )

    def _should_skip(
        self,
        task: AgentTaskV2,
        results: dict[str, AgentResultV2],
        state: dict[str, Any],
        *,
        shadow: bool,
    ) -> bool:
        if task.task_kind is AgentTaskKind.MEMORY_COMMIT and shadow:
            return True
        if task.task_kind is AgentTaskKind.MEMORY_COMMIT:
            if not state.get("memory_authorized", False):
                return True
            if any(
                results[parent].status in {NodeStatus.FAILED, NodeStatus.SKIPPED}
                for parent in task.depends_on
            ):
                return True
        if task.task_kind is AgentTaskKind.RETRIEVE_AND_RANK:
            constraints = state["canonical_understanding"].constraints
            if constraints is None or constraints.category_id.value is None:
                return True
        if task.task_kind in {AgentTaskKind.EXPLAIN, AgentTaskKind.MEMORY_PREPARE}:
            return any(
                results[parent].status in {NodeStatus.FAILED, NodeStatus.SKIPPED}
                for parent in task.depends_on
            )
        return False

    def _prepare_task(
        self,
        task: AgentTaskV2,
        results: dict[str, AgentResultV2],
        state: dict[str, Any],
    ) -> AgentTaskV2:
        understanding = state["canonical_understanding"]
        if task.task_kind is AgentTaskKind.RETRIEVE_AND_RANK and isinstance(
            task.input, RetrievalTaskInput
        ):
            task = task.model_copy(
                update={
                    "input": task.input.model_copy(
                        update={
                            "constraints": understanding.constraints or task.input.constraints,
                            "recognition": understanding.recognition,
                        }
                    )
                }
            )
        elif task.task_kind is AgentTaskKind.EXPLAIN and isinstance(
            task.input, ExplanationTaskInput
        ):
            retrieval = next(
                (
                    result
                    for result in reversed(list(results.values()))
                    if result.task_kind is AgentTaskKind.RETRIEVE_AND_RANK
                ),
                None,
            )
            output = retrieval.output if retrieval is not None else None
            ranked = output.ranked_groups if isinstance(output, RetrievalTaskOutput) else []
            task = task.model_copy(
                update={
                    "input": task.input.model_copy(
                        update={
                            "ranked_groups": ranked,
                            "constraints": understanding.constraints or task.input.constraints,
                        }
                    )
                }
            )
        elif task.task_kind is AgentTaskKind.MEMORY_PREPARE and isinstance(
            task.input, MemoryTaskInput
        ):
            directives = (
                list(understanding.intent_patch.memory_directives)
                if understanding.intent_patch
                else []
            )
            task = task.model_copy(
                update={"input": task.input.model_copy(update={"directives": directives})}
            )
        elif task.task_kind is AgentTaskKind.MEMORY_COMMIT and isinstance(
            task.input, MemoryTaskInput
        ):
            prepare = next(
                (
                    result
                    for result in results.values()
                    if result.task_kind is AgentTaskKind.MEMORY_PREPARE
                ),
                None,
            )
            mutations = list(prepare.proposed_memory_mutations) if prepare is not None else []
            task = task.model_copy(
                update={"input": task.input.model_copy(update={"mutations": mutations})}
            )
        return task

    def _reconcile(self, results: dict[str, AgentResultV2], state: dict[str, Any]) -> None:
        request = state["current_request"]
        recognition = None
        intent = None
        memories: list[MemoryRecord] = []
        for result in results.values():
            if isinstance(result.output, RecognitionTaskOutput):
                recognition = result.output.recognition or recognition
            elif isinstance(result.output, IntentTaskOutput):
                intent = result.output.patch
            elif (
                isinstance(result.output, MemoryTaskOutput)
                and result.task_kind is AgentTaskKind.MEMORY_RECALL
            ):
                memories.extend(result.output.records)
        previous = state["canonical_understanding"].constraints
        merger = ConstraintMerger(self._deps.taxonomy)
        merged = merger.merge(
            prev=previous,
            vision=recognition,
            intent=intent,
            correction=request.correction,
            new_subject=request.image is not None,
            turn_id=str(state["turn_id"]),
            subject_id=None,
        )
        constraints = (
            apply_memory_defaults(merged.constraints, memories) if memories else merged.constraints
        )
        state["canonical_understanding"] = CanonicalUnderstanding(
            recognition=recognition,
            intent_patch=intent,
            constraints=constraints,
            memory_records=memories,
        )
        if merged.notices:
            state["notices"] = [*list(state.get("notices") or []), *merged.notices]

    @staticmethod
    def _build_response(
        request: AgentRequest,
        state: dict[str, Any],
        results: dict[str, AgentResultV2],
    ) -> AgentResponse | None:
        understanding = state["canonical_understanding"]
        constraints = understanding.constraints
        if constraints is None or constraints.category_id.value is None:
            if not any(
                result.task_kind is AgentTaskKind.PARSE_INTENT for result in results.values()
            ):
                return None
            clarification = ClarificationBuilder().build(
                question_id=f"q:{request.request_id}",
                subject_id="",
                turn_id=str(state["turn_id"]),
                reason_code="MISSING_CATEGORY",
                taxonomy=None,
            )
            return AgentResponse(
                session_id=request.session_id,
                request_id=request.request_id,
                turn_id=str(state["turn_id"]),
                status=AgentStatus.CLARIFICATION,
                message="需要补充信息后继续比价。",
                recognition=understanding.recognition,
                effective_constraints=constraints,
                clarification=clarification,
                notices=list(state.get("notices") or []),
                trace_id=str(state["trace_id"]),
            )
        retrieval = next(
            (
                result
                for result in reversed(list(results.values()))
                if result.task_kind is AgentTaskKind.RETRIEVE_AND_RANK
            ),
            None,
        )
        if retrieval is None:
            return None
        if retrieval.status is NodeStatus.FAILED:
            return AgentResponse(
                session_id=request.session_id,
                request_id=request.request_id,
                turn_id=str(state["turn_id"]),
                status=AgentStatus.FAILED,
                message="检索服务不可用，请稍后重试。",
                recognition=understanding.recognition,
                effective_constraints=constraints,
                notices=list(state.get("notices") or []),
                trace_id=str(state["trace_id"]),
            )
        retrieval_output = retrieval.output
        ranked = (
            retrieval_output.ranked_groups
            if isinstance(retrieval_output, RetrievalTaskOutput)
            else []
        )
        explanation = next(
            (
                result
                for result in reversed(list(results.values()))
                if result.task_kind is AgentTaskKind.EXPLAIN
            ),
            None,
        )
        if not ranked:
            status = AgentStatus.NO_RESULTS
            message = "当前条件下没有符合要求的比价结果。"
        else:
            status = AgentStatus.SUCCESS
            message = "已为您完成比价。"
        if explanation is not None and isinstance(explanation.output, ExplanationTaskOutput):
            message = explanation.output.explanation_text or message
            for group in ranked:
                group.explanation = explanation.output.explanation_text
                group.explanation_verified = bool(explanation.output.verified)
        return AgentResponse(
            session_id=request.session_id,
            request_id=request.request_id,
            turn_id=str(state["turn_id"]),
            status=status,
            message=message,
            recognition=understanding.recognition,
            effective_constraints=constraints,
            groups=ranked,
            notices=list(state.get("notices") or []),
            trace_id=str(state["trace_id"]),
        )
