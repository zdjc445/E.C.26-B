"""确定性 Supervisor Planner 与计划校验器。"""

from __future__ import annotations

import hashlib
import json
from asyncio import TimeoutError as AsyncTimeoutError
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import ValidationError

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
from shijiajing_agent.errors import (
    HandoffRejectedError,
    ModelOutputInvalidError,
    PlanValidationError,
)
from shijiajing_agent.multi_agent.capabilities import TASK_CAPABILITIES
from shijiajing_agent.multi_agent.planner_contracts import PlanningOutcome


def _deadline(seconds: float) -> str:
    return (datetime.now(UTC) + timedelta(seconds=seconds)).isoformat()


def plan_hash(plan: ExecutionPlan) -> str:
    payload = json.dumps(plan.model_dump(mode="json"), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


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
        task_budget = AgentTaskBudget(max_retries=1)
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
                if task.plan_id != plan.plan_id:
                    raise PlanValidationError("任务 plan_id 与 ExecutionPlan 不一致")
                if task.task_kind not in TASK_CAPABILITIES:
                    raise PlanValidationError("任务类型不在 allowlist")
                if (
                    task.budget.max_seconds > plan.budget.max_seconds
                    or task.budget.max_model_calls > plan.budget.max_model_calls
                    or task.budget.max_tokens > plan.budget.max_tokens
                ):
                    raise PlanValidationError("任务预算超过 Supervisor 计划预算")
                if task.task_kind is AgentTaskKind.RETRIEVE_AND_RANK and not any(
                    parent in task_map
                    and task_map[parent].task_kind is AgentTaskKind.PARSE_INTENT
                    for parent in task.depends_on
                ):
                    raise PlanValidationError("Retrieval 必须依赖 Intent")
                if task.task_kind is AgentTaskKind.EXPLAIN and not any(
                    parent in task_map
                    and task_map[parent].task_kind is AgentTaskKind.RETRIEVE_AND_RANK
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
        except (TypeError, ValueError, ValidationError, KeyError) as exc:
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
        known_ids = {task.task_id for task in request.plan.tasks}
        if retry_ids - known_ids:
            raise PlanValidationError("replan 包含未知 failed_task_id")
        retry_tasks: list[AgentTaskV2] = []
        replacements: dict[str, str] = {}
        for task in request.plan.tasks:
            if task.task_id not in retry_ids:
                continue
            retry_id = f"{task.task_id}:retry:{task.attempt + 1}"
            replacements[task.task_id] = retry_id
            retry_tasks.append(
                task.model_copy(
                    update={
                        "task_id": retry_id,
                        "parent_task_id": task.task_id,
                        "attempt": task.attempt + 1,
                        "idempotency_key": f"{task.idempotency_key}:retry:{task.attempt + 1}",
                    }
                )
            )
        if retry_tasks:
            retried_by_id = {task.task_id: task for task in retry_tasks}
            replaced_tasks: list[AgentTaskV2] = []
            for task in request.plan.tasks:
                dependencies = [replacements.get(parent, parent) for parent in task.depends_on]
                replaced_tasks.append(task.model_copy(update={"depends_on": dependencies}))
            replaced_tasks.extend(retried_by_id.values())
            PlanValidator().validate(request.plan.model_copy(update={"tasks": replaced_tasks}))
        return ExecutionPlanPatch(
            retry_task_ids=sorted(retry_ids),
            add_tasks=retry_tasks,
            replace_task_ids=replacements,
        )


class GuardedSupervisorPlanner:
    """可选结构化 Planner 的安全门面；每次回退都保留类型化 outcome。"""

    def __init__(
        self,
        deterministic: DeterministicPlanner,
        candidate: Any | None = None,
        mode: str = "active",
    ) -> None:
        self._deterministic = deterministic
        self._candidate = candidate
        self._mode = mode
        self._last_outcome: PlanningOutcome | None = None

    @property
    def last_outcome(self) -> PlanningOutcome | None:
        """最近一次 create/replan 结果；不包含模型原始输出。"""
        return self._last_outcome

    async def create_plan(self, request: SupervisorPlanningInput) -> ExecutionPlan:
        started = datetime.now(UTC)
        base = self._deterministic.create_plan(
            request.request,
            context=request.execution_context,
            taxonomy_version=request.taxonomy_version,
        )
        model_enabled = self._candidate is not None and self._mode in {"shadow", "active"}
        if model_enabled:
            try:
                proposed = await self._candidate.create_plan(request)
                accepted = PlanValidator().validate(proposed)
                if self._mode == "shadow":
                    self._last_outcome = self._outcome(
                        operation="create",
                        plan=base,
                        source="deterministic",
                        model_attempted=True,
                        accepted=False,
                        fallback_reason="MODEL_PLAN_SHADOWED",
                        duration_ms=(datetime.now(UTC) - started).total_seconds() * 1000,
                    )
                    return base
                self._last_outcome = self._outcome(
                    operation="create",
                    plan=accepted,
                    source="model",
                    model_attempted=True,
                    accepted=True,
                    duration_ms=(datetime.now(UTC) - started).total_seconds() * 1000,
                )
                return accepted
            except Exception as exc:
                self._record_fallback(
                    operation="create",
                    plan=base,
                    started=started,
                    exc=exc,
                )
                return base
        self._last_outcome = self._outcome(
            operation="create",
            plan=base,
            source="deterministic",
            model_attempted=False,
            accepted=False,
            fallback_reason="MODEL_DISABLED",
            duration_ms=(datetime.now(UTC) - started).total_seconds() * 1000,
        )
        return base

    async def revise_plan(self, request: SupervisorReplanningInput) -> ExecutionPlanPatch:
        started = datetime.now(UTC)
        model_enabled = self._candidate is not None and self._mode in {
            "shadow",
            "active_replan",
            "active",
        }
        if model_enabled:
            try:
                proposed = await self._candidate.revise_plan(request)
                updated = apply_plan_patch(request.plan, proposed)
                if self._mode == "shadow":
                    fallback = await DeterministicSupervisorPlanner(
                        self._deterministic
                    ).revise_plan(request)
                    shadow_updated = apply_plan_patch(request.plan, fallback)
                    self._last_outcome = self._outcome(
                        operation="replan",
                        plan=shadow_updated,
                        source="deterministic",
                        model_attempted=True,
                        accepted=False,
                        fallback_reason="MODEL_PLAN_SHADOWED",
                        duration_ms=(datetime.now(UTC) - started).total_seconds() * 1000,
                    )
                    return fallback
                self._last_outcome = self._outcome(
                    operation="replan",
                    plan=updated,
                    source="model",
                    model_attempted=True,
                    accepted=True,
                    duration_ms=(datetime.now(UTC) - started).total_seconds() * 1000,
                )
                return proposed
            except Exception as exc:
                fallback = await DeterministicSupervisorPlanner(self._deterministic).revise_plan(
                    request
                )
                updated = apply_plan_patch(request.plan, fallback)
                self._record_fallback(
                    operation="replan",
                    plan=updated,
                    started=started,
                    exc=exc,
                )
                return fallback
        fallback = await DeterministicSupervisorPlanner(self._deterministic).revise_plan(request)
        updated = apply_plan_patch(request.plan, fallback)
        self._last_outcome = self._outcome(
            operation="replan",
            plan=updated,
            source="deterministic",
            model_attempted=False,
            accepted=False,
            fallback_reason="MODEL_DISABLED",
            duration_ms=(datetime.now(UTC) - started).total_seconds() * 1000,
        )
        return fallback

    def _record_fallback(
        self,
        *,
        operation: str,
        plan: ExecutionPlan,
        started: datetime,
        exc: Exception,
    ) -> None:
        reason = "MODEL_NETWORK_ERROR"
        if isinstance(exc, (TimeoutError, AsyncTimeoutError)):
            reason = "MODEL_TIMEOUT"
        elif isinstance(exc, ModelOutputInvalidError):
            reason = "MODEL_OUTPUT_INVALID"
        elif isinstance(exc, PlanValidationError):
            reason = "PLAN_VALIDATION_FAILED"
        self._last_outcome = self._outcome(
            operation=operation,
            plan=plan,
            source="deterministic",
            model_attempted=True,
            accepted=False,
            fallback_reason=reason,  # type: ignore[arg-type]
            duration_ms=(datetime.now(UTC) - started).total_seconds() * 1000,
        )

    def _outcome(
        self,
        *,
        operation: str,
        plan: ExecutionPlan,
        source: str,
        model_attempted: bool,
        accepted: bool,
        duration_ms: float,
        fallback_reason: str | None = None,
    ) -> PlanningOutcome:
        model = getattr(self._candidate, "model_name", None) if self._candidate else None
        prompt_version = (
            getattr(self._candidate, "prompt_version", None) if self._candidate else None
        )
        repair_count = int(getattr(self._candidate, "repair_count", 0) or 0)
        token_usage = dict(getattr(self._candidate, "token_usage", {}) or {})
        proposal_hash = getattr(self._candidate, "proposal_hash", None) if self._candidate else None
        return PlanningOutcome(
            operation=operation,  # type: ignore[arg-type]
            plan=plan,
            source=source,  # type: ignore[arg-type]
            model_attempted=model_attempted,
            accepted=accepted,
            fallback_reason=fallback_reason,  # type: ignore[arg-type]
            model=model,
            prompt_version=prompt_version,
            repair_count=repair_count,
            duration_ms=max(0.0, duration_ms),
            proposal_hash=proposal_hash,
            plan_hash=plan_hash(plan),
            token_usage=token_usage,
            action_count=0,
            task_count=len(plan.tasks),
        )


def apply_plan_patch(plan: ExecutionPlan, patch: ExecutionPlanPatch) -> ExecutionPlan:
    """将结构化 replan patch 应用到计划，并重新校验依赖。"""
    PlanValidator().validate(plan)
    existing = {task.task_id: task for task in plan.tasks}
    skip_ids = set(patch.skip_task_ids)
    retry_ids = set(patch.retry_task_ids)
    replacement_ids = dict(patch.replace_task_ids)
    if len(skip_ids) != len(patch.skip_task_ids):
        raise PlanValidationError("skip_task_ids 不得重复")
    if len(retry_ids) != len(patch.retry_task_ids):
        raise PlanValidationError("retry_task_ids 不得重复")
    if skip_ids & set(replacement_ids):
        raise PlanValidationError("同一任务不能同时 skip 和 replace")
    if skip_ids - set(existing):
        raise PlanValidationError("skip_task_ids 包含未知任务")
    if retry_ids - set(existing):
        raise PlanValidationError("retry_task_ids 包含未知任务")
    add_ids = [task.task_id for task in patch.add_tasks]
    if len(add_ids) != len(set(add_ids)):
        raise PlanValidationError("add_tasks task_id 不得重复")
    if set(add_ids) & set(existing):
        raise PlanValidationError("add_tasks task_id 与已有任务重复")
    if set(retry_ids) - set(replacement_ids):
        raise PlanValidationError("retry_task_ids 必须通过 replace_task_ids 指向新任务")
    if set(replacement_ids) - set(existing):
        raise PlanValidationError("replace_task_ids 源任务不存在")
    if set(replacement_ids.values()) - set(add_ids):
        raise PlanValidationError("replace_task_ids 目标必须来自 add_tasks")
    if set(replacement_ids) & set(add_ids):
        raise PlanValidationError("replace_task_ids 目标不能同时作为源任务")
    if any(source == target for source, target in replacement_ids.items()):
        raise PlanValidationError("replace_task_ids 不能自替换")
    if skip_ids & retry_ids:
        raise PlanValidationError("同一任务不能同时 skip 和 retry")
    for task in plan.tasks:
        for dependency in task.depends_on:
            resolved = replacement_ids.get(dependency, dependency)
            if resolved in skip_ids:
                raise PlanValidationError(f"不能跳过仍被依赖的任务: {dependency}")
    for task in patch.add_tasks:
        if task.plan_id != plan.plan_id:
            raise PlanValidationError("patch 新任务 plan_id 与计划不一致")
        existing[task.task_id] = task
    tasks: list[AgentTaskV2] = []
    for task in existing.values():
        if task.task_id in skip_ids or task.task_id in replacement_ids:
            continue
        dependencies = [patch.replace_task_ids.get(parent, parent) for parent in task.depends_on]
        tasks.append(task.model_copy(update={"depends_on": dependencies}))
    return PlanValidator().validate(plan.model_copy(update={"tasks": tasks}))


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
