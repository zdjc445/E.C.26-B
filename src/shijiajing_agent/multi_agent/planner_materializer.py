"""把模型 Planner 提议安全物化为计划 patch。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from shijiajing_agent.contracts import (
    AgentTaskKind,
    AgentTaskV2,
    ExecutionPlan,
    ExecutionPlanPatch,
    ExplanationTaskInput,
    RetrievalTaskInput,
)
from shijiajing_agent.errors import PlanValidationError
from shijiajing_agent.multi_agent.planner import apply_plan_patch
from shijiajing_agent.multi_agent.planner_catalog import AllowedAction, AllowedActionCatalog
from shijiajing_agent.multi_agent.planner_contracts import PlannerAction, PlannerProposal


class MaterializationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["plan", "patch"]
    plan: ExecutionPlan
    patch: ExecutionPlanPatch


class PlanMaterializer:
    """只从基础计划和目录授权引用构造 AgentTaskV2。"""

    def materialize_plan(
        self, base_plan: ExecutionPlan, catalog: AllowedActionCatalog, proposal: PlannerProposal
    ) -> ExecutionPlan:
        result = self.materialize_patch(base_plan, catalog, proposal)
        return result.plan

    def materialize_patch(
        self, base_plan: ExecutionPlan, catalog: AllowedActionCatalog, proposal: PlannerProposal
    ) -> MaterializationResult:
        if proposal.base_plan_id != base_plan.plan_id or catalog.base_plan_id != base_plan.plan_id:
            raise PlanValidationError("Planner proposal/catalog 与基础计划不匹配")
        entries = catalog.by_id()
        if len(entries) != len(catalog.actions):
            raise PlanValidationError("AllowedActionCatalog action_id 必须唯一")
        seen: set[str] = set()
        target_actions: dict[str, list[PlannerAction]] = {}
        for action in proposal.actions:
            if action.action_id in seen:
                raise PlanValidationError("Planner proposal 不得重复选择 action")
            seen.add(action.action_id)
            entry = entries.get(action.action_id)
            if entry is None:
                raise PlanValidationError(f"ACTION_NOT_ALLOWED: {action.action_id}")
            self._validate_action_matches_entry(action, entry)
            if action.action != "keep" and action.target_task_id is not None:
                target_actions.setdefault(action.target_task_id, []).append(action)

        for target, actions in target_actions.items():
            if len(actions) > 1:
                raise PlanValidationError(f"任务存在互斥 Planner 动作: {target}")

        task_map = {task.task_id: task for task in base_plan.tasks}
        skip_ids: set[str] = set()
        retry_ids: list[str] = []
        add_tasks: list[AgentTaskV2] = []
        replacements: dict[str, str] = {}
        for action in proposal.actions:
            if action.action == "keep":
                continue
            assert action.target_task_id is not None
            target = action.target_task_id
            task = task_map.get(target)
            if task is None:
                raise PlanValidationError(f"Planner target task 不存在: {target}")
            entry = entries[action.action_id]
            if action.action == "skip":
                if not entry.can_skip:
                    raise PlanValidationError(f"ACTION_NOT_ALLOWED: {action.action_id}")
                skip_ids.add(target)
                continue
            if action.action == "retry":
                if not entry.can_retry or task.attempt >= entry.max_attempt:
                    raise PlanValidationError(f"Planner retry 超出 attempt 预算: {target}")
                retry_id = f"{target}:retry:{task.attempt + 1}"
                retry_task = task.model_copy(
                    update={
                        "task_id": retry_id,
                        "parent_task_id": target,
                        "attempt": task.attempt + 1,
                        "idempotency_key": f"{task.idempotency_key}:retry:{task.attempt + 1}",
                    }
                )
                retry_ids.append(target)
                add_tasks.append(retry_task)
                replacements[target] = retry_id
                continue
            if action.action == "add_template":
                replacement = self._materialize_template(base_plan, task, entry)
                add_tasks.append(replacement)
                replacements[target] = replacement.task_id
                continue
            raise PlanValidationError(f"未知 Planner action: {action.action}")

        self._validate_skip_safety(base_plan, skip_ids, replacements)
        patch = ExecutionPlanPatch(
            skip_task_ids=sorted(skip_ids),
            retry_task_ids=sorted(retry_ids),
            add_tasks=add_tasks,
            replace_task_ids=replacements,
        )
        plan = apply_plan_patch(base_plan, patch)
        return MaterializationResult(kind="patch", plan=plan, patch=patch)

    @staticmethod
    def _validate_action_matches_entry(action: PlannerAction, entry: AllowedAction) -> None:
        if action.action != entry.action:
            raise PlanValidationError(f"Planner action 类型与目录不一致: {action.action_id}")
        if action.target_task_id != entry.target_task_id:
            raise PlanValidationError(f"Planner target 与目录不一致: {action.action_id}")
        if action.template_id != entry.template_id:
            raise PlanValidationError(f"Planner template 与目录不一致: {action.action_id}")

    @staticmethod
    def _validate_skip_safety(
        plan: ExecutionPlan, skip_ids: set[str], replacements: dict[str, str]
    ) -> None:
        task_ids = {task.task_id for task in plan.tasks}
        for task in plan.tasks:
            for dependency in task.depends_on:
                resolved = replacements.get(dependency, dependency)
                if resolved in skip_ids or (dependency in skip_ids and resolved == dependency):
                    raise PlanValidationError(f"不能跳过仍被依赖的任务: {dependency}")
        if skip_ids - task_ids:
            raise PlanValidationError("skip_task_ids 包含未知任务")

    @staticmethod
    def _materialize_template(
        plan: ExecutionPlan, target: AgentTaskV2, entry: AllowedAction
    ) -> AgentTaskV2:
        template_id = entry.template_id
        if template_id == "template-explanation-fallback":
            if target.task_kind is not AgentTaskKind.EXPLAIN or not isinstance(
                target.input, ExplanationTaskInput
            ):
                raise PlanValidationError("explanation fallback template 目标无效")
            input_value = target.input.model_copy(deep=True)
        elif template_id == "template-retrieval-recognition-relaxation":
            if target.task_kind is not AgentTaskKind.RETRIEVE_AND_RANK or not isinstance(
                target.input, RetrievalTaskInput
            ):
                raise PlanValidationError("retrieval relaxation template 目标无效")
            input_value = target.input.model_copy(update={"recognition": None})
        else:
            raise PlanValidationError(f"未知 Planner template: {template_id}")
        task_id = f"{plan.plan_id}:{template_id.removeprefix('template-')}"
        return target.model_copy(
            update={
                "task_id": task_id,
                "parent_task_id": target.task_id,
                "attempt": target.attempt + 1,
                "idempotency_key": f"{target.idempotency_key}:template:{template_id}",
                "input": input_value,
            }
        )
