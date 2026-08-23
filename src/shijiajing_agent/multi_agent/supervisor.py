"""受控层级式 Supervisor 执行器。

它只负责计划、barrier、结果归并、规范约束和副作用授权。五个 Specialist 通过 registry
接收最小任务输入，结果统一以 ``AgentResultV2`` 返回。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from time import perf_counter
from typing import Any, cast

from shijiajing_agent.contracts import (
    AgentExecutionContext,
    AgentRequest,
    AgentResponse,
    AgentResultV2,
    AgentStatus,
    AgentTaskKind,
    AgentTaskV2,
    CanonicalUnderstanding,
    ExecutionPlan,
    ExplanationTaskInput,
    ExplanationTaskOutput,
    IntentTaskOutput,
    MemoryRecord,
    MemoryTaskInput,
    MemoryTaskOutput,
    NodeStatus,
    RecognitionTaskOutput,
    RetrievalTaskInput,
    RetrievalTaskOutput,
    SupervisorBudgetUsage,
    TaskRecord,
)
from shijiajing_agent.domain.constraints import ClarificationBuilder, ConstraintMerger
from shijiajing_agent.domain.memory_policy import apply_memory_defaults
from shijiajing_agent.errors import PlanValidationError
from shijiajing_agent.multi_agent.agents.base import fixed_error, result_for
from shijiajing_agent.multi_agent.checkpoint import (
    MultiAgentCheckpointPort,
    agent_task_checkpoint_namespace,
    supervisor_checkpoint_namespace,
)
from shijiajing_agent.multi_agent.planner import DeterministicPlanner, PlanValidator
from shijiajing_agent.multi_agent.registry import SpecialistAgentRegistry, build_registry
from shijiajing_agent.state import SupervisorState, merge_task_results


@dataclass(frozen=True)
class SupervisorRunResult:
    state: SupervisorState
    response: AgentResponse
    plan: ExecutionPlan


class MultiAgentSupervisor:
    """运行一个受控计划；同一 Supervisor 实例不持有 Specialist 私有状态。"""

    def __init__(
        self,
        deps: Any,
        *,
        registry: SpecialistAgentRegistry | None = None,
        planner: DeterministicPlanner | None = None,
        checkpoint: MultiAgentCheckpointPort | None = None,
    ) -> None:
        self._deps = deps
        self._registry = registry or build_registry(deps)
        self._planner = planner or DeterministicPlanner(
            max_tasks=getattr(deps.settings, "max_agent_tasks", 32),
            max_replans=getattr(deps.settings, "max_supervisor_replans", 2),
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
    ) -> SupervisorRunResult:
        context = context or AgentExecutionContext()
        plan = PlanValidator().validate(self.create_plan(request, context=context))
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
            "task_records": task_records,
            "task_results": {},
            "canonical_understanding": CanonicalUnderstanding(),
            "replan_count": 0,
            "total_task_count": 0,
            "budget_usage": SupervisorBudgetUsage(),
            "notices": [],
            "events": [],
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
                returned: list[AgentResultV2 | BaseException] = list(
                    await asyncio.gather(
                        *(self._dispatch(task) for task in dispatchable),
                        return_exceptions=True,
                    )
                )
                for task, item in zip(dispatchable, returned, strict=True):
                    if isinstance(item, BaseException):
                        result = result_for(
                            task,
                            status=NodeStatus.FAILED,
                            error=fixed_error(
                                "AGENT_EXECUTION_FAILED", "Agent 执行失败", retryable=True
                            ),
                        )
                    else:
                        result = item
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
            state["task_results"] = results
            if self._checkpoint is not None:
                checkpoint_version = await self._checkpoint.save_supervisor(
                    checkpoint_namespace,
                    cast(SupervisorState, state),
                    checkpoint_version,
                )
            response = self._build_response(request, state, results)
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

    async def _dispatch(self, task: AgentTaskV2) -> AgentResultV2:
        return await self._registry.dispatch(task)

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
            if state.get("final_response") is None:
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
                    for result in results.values()
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
                for result in results.values()
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
            (result for result in results.values() if result.task_kind is AgentTaskKind.EXPLAIN),
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
