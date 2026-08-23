"""确定性 Supervisor Planner 与计划校验器。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from shijiajing_agent.contracts import (
    AgentExecutionContext,
    AgentRequest,
    AgentTaskBudget,
    AgentTaskInput,
    AgentTaskKind,
    AgentTaskV2,
    ExecutionPlan,
    ExecutionPlanPatch,
    ExplanationTaskInput,
    HandoffRequest,
    IntentTaskInput,
    MemoryTaskInput,
    RecognitionTaskInput,
    RetrievalTaskInput,
    ShoppingConstraints,
    SpecialistAgentName,
    SupervisorPlanningInput,
    SupervisorReplanningInput,
)
from shijiajing_agent.errors import HandoffRejectedError, PlanValidationError
from shijiajing_agent.multi_agent.capabilities import TASK_CAPABILITIES


def _deadline(seconds: float) -> str:
    return (datetime.now(UTC) + timedelta(seconds=seconds)).isoformat()


class DeterministicPlanner:
    """根据输入形态生成固定 DAG；不读取模型输出也不改变硬过滤。"""

    def __init__(self, *, max_tasks: int = 32, max_replans: int = 2) -> None:
        self.max_tasks = max_tasks
        self.max_replans = max_replans

    def create_plan(
        self,
        request: AgentRequest,
        *,
        context: AgentExecutionContext | None = None,
        taxonomy_version: str = "unknown",
        plan_id: str | None = None,
    ) -> ExecutionPlan:
        plan_id = plan_id or f"plan:{request.session_id}:{request.request_id}"
        task_budget = AgentTaskBudget()
        tasks: list[AgentTaskV2] = []

        def add(
            task_id: str,
            agent: SpecialistAgentName,
            kind: AgentTaskKind,
            input_value: Any,
            dependencies: list[str] | None = None,
        ) -> None:
            tasks.append(
                AgentTaskV2(
                    plan_id=plan_id,
                    task_id=task_id,
                    agent_name=agent,
                    task_kind=kind,
                    depends_on=dependencies or [],
                    idempotency_key=f"{plan_id}:{task_id}:1",
                    deadline_at=_deadline(task_budget.max_seconds),
                    budget=task_budget,
                    input=input_value,
                )
            )

        recognition_id: str | None = None
        if request.image is not None or request.correction is not None:
            recognition_id = f"{plan_id}:recognition"
            kind = (
                AgentTaskKind.APPLY_CORRECTION
                if request.correction is not None
                else AgentTaskKind.RECOGNIZE
            )
            add(
                recognition_id,
                SpecialistAgentName.RECOGNITION,
                kind,
                RecognitionTaskInput(
                    image=request.image,
                    correction=request.correction,
                    taxonomy_version=taxonomy_version,
                ),
            )

        intent_id = f"{plan_id}:intent"
        add(
            intent_id,
            SpecialistAgentName.INTENT,
            AgentTaskKind.PARSE_INTENT,
            IntentTaskInput(text=request.text, selected_option_id=request.selected_option_id),
        )

        memory_id: str | None = None
        if context is not None and context.memory_enabled and context.memory_owner_id:
            memory_id = f"{plan_id}:memory-recall"
            add(
                memory_id,
                SpecialistAgentName.MEMORY,
                AgentTaskKind.MEMORY_RECALL,
                MemoryTaskInput(
                    operation="recall",
                    session_id=request.session_id,
                    request_id=request.request_id,
                    memory_owner_id=context.memory_owner_id,
                    query=None,
                ),
            )

        retrieval_dependencies = [intent_id]
        if recognition_id:
            retrieval_dependencies.append(recognition_id)
        if memory_id:
            retrieval_dependencies.append(memory_id)
        retrieval_id = f"{plan_id}:retrieval"
        add(
            retrieval_id,
            SpecialistAgentName.RETRIEVAL,
            AgentTaskKind.RETRIEVE_AND_RANK,
            RetrievalTaskInput(constraints=ShoppingConstraints(), query_text=request.text or ""),
            retrieval_dependencies,
        )
        explanation_id = f"{plan_id}:explanation"
        add(
            explanation_id,
            SpecialistAgentName.EXPLANATION,
            AgentTaskKind.EXPLAIN,
            ExplanationTaskInput(constraints=ShoppingConstraints()),
            [retrieval_id],
        )

        if memory_id:
            prepare_id = f"{plan_id}:memory-prepare"
            add(
                prepare_id,
                SpecialistAgentName.MEMORY,
                AgentTaskKind.MEMORY_PREPARE,
                MemoryTaskInput(
                    operation="prepare",
                    session_id=request.session_id,
                    request_id=request.request_id,
                    memory_owner_id=context.memory_owner_id if context else None,
                ),
                [intent_id, explanation_id],
            )
            add(
                f"{plan_id}:memory-commit",
                SpecialistAgentName.MEMORY,
                AgentTaskKind.MEMORY_COMMIT,
                MemoryTaskInput(
                    operation="commit",
                    session_id=request.session_id,
                    request_id=request.request_id,
                    memory_owner_id=context.memory_owner_id if context else None,
                    authorization_id=f"auth:{plan_id}",
                ),
                [prepare_id],
            )

        plan = ExecutionPlan(
            plan_id=plan_id,
            tasks=tasks,
            max_tasks=self.max_tasks,
            max_replans=self.max_replans,
            budget=AgentTaskBudget(max_seconds=60.0, max_model_calls=20, max_tokens=100_000),
        )
        return PlanValidator().validate(plan)

    def revise_plan(self, plan: ExecutionPlan, *, skip_task_ids: set[str]) -> ExecutionPlan:
        """只允许 Supervisor 删除任务；不允许 planner 改写已有 input。"""
        remaining = [task for task in plan.tasks if task.task_id not in skip_task_ids]
        remaining_ids = {task.task_id for task in remaining}
        for task in remaining:
            if set(task.depends_on) - remaining_ids:
                raise PlanValidationError("不能跳过仍被依赖的任务")
        return PlanValidator().validate(plan.model_copy(update={"tasks": remaining}))


class PlanValidator:
    """确定性计划门禁，模型 Planner 的结果也必须经过此处。"""

    def validate(self, plan: ExecutionPlan) -> ExecutionPlan:
        try:
            plan = ExecutionPlan.model_validate(plan)
            task_map = {task.task_id: task for task in plan.tasks}
            for task in plan.tasks:
                if task.task_kind not in TASK_CAPABILITIES:
                    raise PlanValidationError("任务类型不在 allowlist")
                if task.task_kind is AgentTaskKind.RETRIEVE_AND_RANK and not any(
                    task_map[parent].task_kind is AgentTaskKind.PARSE_INTENT
                    for parent in task.depends_on
                ):
                    raise PlanValidationError("Retrieval 必须依赖 Intent")
                if task.task_kind is AgentTaskKind.EXPLAIN and not any(
                    task_map[parent].task_kind is AgentTaskKind.RETRIEVE_AND_RANK
                    for parent in task.depends_on
                ):
                    raise PlanValidationError("Explanation 必须依赖 Retrieval")
                if task.task_kind is AgentTaskKind.MEMORY_COMMIT:
                    if (
                        not isinstance(task.input, MemoryTaskInput)
                        or not task.input.authorization_id
                    ):
                        raise PlanValidationError(
                            "Memory commit 必须携带 Supervisor authorization_id"
                        )
            return plan
        except PlanValidationError:
            raise
        except (TypeError, ValueError) as exc:
            raise PlanValidationError(str(exc)) from exc


class DeterministicSupervisorPlanner:
    """实现 ``SupervisorPlannerPort`` 的异步适配器。"""

    def __init__(self, planner: DeterministicPlanner | None = None) -> None:
        self._planner = planner or DeterministicPlanner()

    async def create_plan(self, request: SupervisorPlanningInput) -> ExecutionPlan:
        return self._planner.create_plan(
            request.request,
            context=request.execution_context,
            taxonomy_version=request.taxonomy_version,
        )

    async def revise_plan(self, request: SupervisorReplanningInput) -> ExecutionPlanPatch:
        retry_ids = set(request.failed_task_ids)
        retry_tasks = [
            task.model_copy(
                update={
                    "attempt": task.attempt + 1,
                    "idempotency_key": f"{task.idempotency_key}:retry:{task.attempt + 1}",
                }
            )
            for task in request.plan.tasks
            if task.task_id in retry_ids
        ]
        if retry_tasks:
            retried_by_id = {task.task_id: task for task in retry_tasks}
            PlanValidator().validate(
                request.plan.model_copy(
                    update={
                        "tasks": [
                            retried_by_id.get(task.task_id, task) for task in request.plan.tasks
                        ]
                    }
                )
            )
        return ExecutionPlanPatch(
            retry_task_ids=sorted(retry_ids),
            add_tasks=retry_tasks,
        )


def approve_handoff(
    plan: ExecutionPlan,
    request: HandoffRequest,
    *,
    parent_task_id: str,
    current_task_count: int,
    input_value: AgentTaskInput | None = None,
) -> AgentTaskV2:
    """Supervisor 审批 handoff proposal，并返回新任务；Agent 无权直接创建它。"""
    if current_task_count >= plan.max_tasks:
        raise HandoffRejectedError("任务数预算已耗尽")
    if request.target_agent is SpecialistAgentName.MEMORY and request.requested_task_kind not in {
        AgentTaskKind.MEMORY_RECALL,
        AgentTaskKind.MEMORY_PREPARE,
        AgentTaskKind.MEMORY_COMMIT,
    }:
        raise HandoffRejectedError("handoff 目标 Agent 与任务类型不匹配")
    if (
        request.target_agent is SpecialistAgentName.RETRIEVAL
        and request.requested_task_kind
        not in {
            AgentTaskKind.RETRIEVE_AND_RANK,
        }
    ):
        raise HandoffRejectedError("retrieval handoff 只能请求 retrieval.retrieve_and_rank")
    if input_value is None:
        raise HandoffRejectedError("没有可安全构造的 handoff input；必须由 Supervisor 提供授权引用")
    if request.requested_task_kind is AgentTaskKind.MEMORY_COMMIT:
        if not isinstance(input_value, MemoryTaskInput) or not input_value.authorization_id:
            raise HandoffRejectedError("Memory commit handoff 必须携带 Supervisor 授权")
    task = AgentTaskV2(
        plan_id=plan.plan_id,
        task_id=f"{plan.plan_id}:handoff:{current_task_count + 1}",
        parent_task_id=parent_task_id,
        agent_name=request.target_agent,
        task_kind=request.requested_task_kind,
        depends_on=[parent_task_id],
        idempotency_key=f"{plan.plan_id}:handoff:{current_task_count + 1}:1",
        deadline_at=_deadline(plan.budget.max_seconds),
        budget=AgentTaskBudget(max_seconds=plan.budget.max_seconds),
        input=input_value,
    )
    PlanValidator().validate(plan.model_copy(update={"tasks": [*plan.tasks, task]}))
    return task
