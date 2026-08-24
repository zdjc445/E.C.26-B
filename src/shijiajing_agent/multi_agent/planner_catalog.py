"""由确定性 Supervisor 生成的 Planner allowlist 目录。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from shijiajing_agent.contracts import AgentTaskKind, ExecutionPlan
from shijiajing_agent.multi_agent.capabilities import TASK_CAPABILITIES
from shijiajing_agent.multi_agent.planner_contracts import PlannerActionKind


class AllowedAction(BaseModel):
    """一个经过 Supervisor 授权的、可被模型引用的动作。"""

    model_config = ConfigDict(extra="forbid")

    action_id: str = Field(min_length=1, max_length=128)
    action: PlannerActionKind
    target_task_id: str | None = None
    template_id: str | None = None
    required_capabilities: list[str] = Field(default_factory=list[str])
    depends_on: list[str] = Field(default_factory=list[str])
    can_skip: bool = False
    can_retry: bool = False
    max_attempt: int = Field(default=1, ge=1, le=100)
    authorization_ref: str | None = None
    forbidden_reason: str | None = None


class AllowedActionCatalog(BaseModel):
    """模型可见的最小动作目录；不携带用户原文、Memory 内容或完整任务输入。"""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    base_plan_id: str = Field(min_length=1, max_length=128)
    actions: list[AllowedAction] = Field(default_factory=list[AllowedAction], max_length=256)

    def by_id(self) -> dict[str, AllowedAction]:
        return {item.action_id: item for item in self.actions}

    def prompt_payload(self) -> list[dict[str, object]]:
        """返回可直接注入 prompt 的脱敏目录。"""
        return [
            {
                "action_id": item.action_id,
                "action": item.action,
                "target_task_id": item.target_task_id,
                "template_id": item.template_id,
                "depends_on": item.depends_on,
                "can_skip": item.can_skip,
                "can_retry": item.can_retry,
                "max_attempt": item.max_attempt,
                "authorization_ref": item.authorization_ref,
                "forbidden_reason": item.forbidden_reason,
            }
            for item in self.actions
        ]


def build_action_catalog(plan: ExecutionPlan) -> AllowedActionCatalog:
    """从合法基础计划生成稳定动作目录。"""
    task_ids = {task.task_id for task in plan.tasks}
    dependents: dict[str, set[str]] = {task_id: set() for task_id in task_ids}
    for task in plan.tasks:
        for dependency in task.depends_on:
            dependents.setdefault(dependency, set()).add(task.task_id)

    actions: list[AllowedAction] = []
    for task in plan.tasks:
        capabilities = sorted(TASK_CAPABILITIES[task.task_kind])
        actions.append(
            AllowedAction(
                action_id=f"keep:{task.task_id}",
                action="keep",
                target_task_id=task.task_id,
                required_capabilities=capabilities,
                depends_on=list(task.depends_on),
                authorization_ref=f"system:task:{task.task_id}",
            )
        )
        # 只有叶子任务可以独立跳过；跳过中间节点必须同时有 replacement，
        # 而 replacement 由 Materializer 生成，模型不能自行构造。
        if not dependents.get(task.task_id):
            actions.append(
                AllowedAction(
                    action_id=f"skip:{task.task_id}",
                    action="skip",
                    target_task_id=task.task_id,
                    required_capabilities=capabilities,
                    depends_on=list(task.depends_on),
                    can_skip=True,
                    authorization_ref=f"system:task:{task.task_id}",
                )
            )
        if task.attempt <= task.budget.max_retries:
            actions.append(
                AllowedAction(
                    action_id=f"retry:{task.task_id}",
                    action="retry",
                    target_task_id=task.task_id,
                    required_capabilities=capabilities,
                    depends_on=list(task.depends_on),
                    can_retry=True,
                    max_attempt=task.attempt + task.budget.max_retries,
                    authorization_ref=f"system:task:{task.task_id}",
                )
            )

    for task in plan.tasks:
        if task.task_kind is AgentTaskKind.EXPLAIN:
            actions.append(
                AllowedAction(
                    action_id="add:template-explanation-fallback",
                    action="add_template",
                    target_task_id=task.task_id,
                    template_id="template-explanation-fallback",
                    required_capabilities=sorted(TASK_CAPABILITIES[task.task_kind]),
                    depends_on=list(task.depends_on),
                    authorization_ref=f"system:template:explanation:{task.task_id}",
                )
            )
        if task.task_kind is AgentTaskKind.RETRIEVE_AND_RANK:
            actions.append(
                AllowedAction(
                    action_id="add:template-retrieval-recognition-relaxation",
                    action="add_template",
                    target_task_id=task.task_id,
                    template_id="template-retrieval-recognition-relaxation",
                    required_capabilities=sorted(TASK_CAPABILITIES[task.task_kind]),
                    depends_on=list(task.depends_on),
                    authorization_ref=f"system:template:retrieval:{task.task_id}",
                )
            )
    return AllowedActionCatalog(base_plan_id=plan.plan_id, actions=actions)
