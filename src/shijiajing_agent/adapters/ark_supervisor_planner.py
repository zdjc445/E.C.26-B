"""Ark Supervisor Planner：最小输入 + 严格 proposal + 确定性 Materializer。"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from shijiajing_agent.adapters.ark_models import ArkModelClient, load_prompt
from shijiajing_agent.config import Settings
from shijiajing_agent.contracts import (
    AgentTaskKind,
    ExecutionPlan,
    ExecutionPlanPatch,
    SupervisorPlanningInput,
    SupervisorReplanningInput,
)
from shijiajing_agent.domain.taxonomy import Taxonomy
from shijiajing_agent.errors import ModelOutputInvalidError
from shijiajing_agent.multi_agent.planner import DeterministicPlanner
from shijiajing_agent.multi_agent.planner_catalog import (
    AllowedActionCatalog,
    build_action_catalog,
)
from shijiajing_agent.multi_agent.planner_contracts import PlannerProposal
from shijiajing_agent.multi_agent.planner_materializer import PlanMaterializer


class ArkSupervisorPlanner:
    """实现 SupervisorPlannerPort；不直接向模型暴露 AgentTaskV2 输入。"""

    def __init__(self, client: ArkModelClient, taxonomy: Taxonomy, settings: Settings) -> None:
        self._client = client
        self._taxonomy = taxonomy
        self._settings = settings
        self._create_prompt_version, self._create_prompt = load_prompt("supervisor_create_plan.md")
        self._revise_prompt_version, self._revise_prompt = load_prompt("supervisor_revise_plan.md")
        self.model_name = settings.supervisor_model
        self.prompt_version: str | None = None
        self.repair_count = 0
        self.token_usage: dict[str, int] = {}
        self.proposal_hash: str | None = None
        self.action_count = 0

    async def setup(self) -> None:
        return None

    async def close(self) -> None:
        # ArkModelClient 的生命周期由业务模型 owner 管理，避免重复 close。
        return None

    async def create_plan(self, request: SupervisorPlanningInput) -> ExecutionPlan:
        base = request.base_plan or DeterministicPlanner(
            max_tasks=self._settings.max_agent_tasks,
            max_replans=self._settings.max_supervisor_replans,
        ).create_plan(
            request.request,
            context=request.execution_context,
            taxonomy_version=request.taxonomy_version,
        )
        catalog = build_action_catalog(base)
        proposal = await self._call(
            prompt=self._create_prompt,
            prompt_version=self._create_prompt_version,
            payload=self._create_payload(request, base, catalog),
        )
        return PlanMaterializer().materialize_plan(base, catalog, proposal)

    async def revise_plan(self, request: SupervisorReplanningInput) -> ExecutionPlanPatch:
        catalog = build_action_catalog(request.plan)
        failed = set(request.failed_task_ids)
        catalog = AllowedActionCatalog(
            base_plan_id=catalog.base_plan_id,
            actions=[
                action
                for action in catalog.actions
                if action.action == "keep"
                or (action.action == "retry" and action.target_task_id in failed)
                or (
                    action.action == "add_template"
                    and action.target_task_id in failed
                )
            ],
        )
        proposal = await self._call(
            prompt=self._revise_prompt,
            prompt_version=self._revise_prompt_version,
            payload=self._revise_payload(request, catalog),
        )
        return PlanMaterializer().materialize_patch(request.plan, catalog, proposal).patch

    async def _call(
        self,
        *,
        prompt: str,
        prompt_version: str,
        payload: dict[str, Any],
    ) -> PlannerProposal:
        self.prompt_version = prompt_version
        self.repair_count = 0
        self.token_usage = {}
        self.proposal_hash = None
        self.action_count = 0
        obj = await self._client.structured_call(
            node="supervisor_planner",
            model=self.model_name or "",
            prompt_version=prompt_version,
            system_prompt=prompt,
            user_message=json.dumps(payload, ensure_ascii=False, sort_keys=True),
            schema=PlannerProposal,
            timeout_seconds=self._settings.supervisor_planner_timeout_seconds,
            repair_instruction=(
                "只修正 JSON Schema 字段错误和目录引用错误，仍然只能选择 "
                "AllowedActionCatalog 中的 action。"
            ),
            error_kind=ModelOutputInvalidError,
            max_repairs=self._settings.supervisor_planner_max_repairs,
            max_tokens=self._settings.supervisor_planner_max_tokens,
        )
        proposal = PlannerProposal.model_validate(obj)
        self.action_count = len(proposal.actions)
        record = self._client.last_call
        if record is not None:
            self.repair_count = record.repair_count
            self.token_usage = dict(record.token_usage or {})
        self.proposal_hash = hashlib.sha256(
            json.dumps(proposal.model_dump(mode="json"), sort_keys=True).encode("utf-8")
        ).hexdigest()
        return proposal

    @staticmethod
    def _task_summary(plan: Any) -> list[dict[str, Any]]:
        return [
            {
                "task_id": task.task_id,
                "task_kind": task.task_kind.value,
                "agent": task.agent_name.value,
                "depends_on": list(task.depends_on),
                "attempt": task.attempt,
                "terminal": task.task_kind
                in {AgentTaskKind.EXPLAIN, AgentTaskKind.MEMORY_COMMIT},
            }
            for task in plan.tasks
        ]

    def _create_payload(
        self, request: SupervisorPlanningInput, plan: Any, catalog: Any
    ) -> dict[str, Any]:
        user_request = request.request
        return {
            "operation": "create",
            "request_shape": {
                "has_text": bool(user_request.text),
                "has_image": user_request.image is not None,
                "has_correction": user_request.correction is not None,
                "has_selected_option": user_request.selected_option_id is not None,
                "text_length": len(user_request.text or ""),
                "text_preview": (user_request.text or "")[:512] if user_request.text else None,
            },
            "taxonomy_version": request.taxonomy_version,
            "capabilities": {
                "memory_enabled": request.execution_context.memory_enabled,
                "memory_owner_present": bool(request.execution_context.memory_owner_id),
            },
            "base_plan": {"plan_id": plan.plan_id, "tasks": self._task_summary(plan)},
            "allowed_actions": catalog.prompt_payload(),
        }

    def _revise_payload(
        self, request: SupervisorReplanningInput, catalog: Any
    ) -> dict[str, Any]:
        failed: list[dict[str, Any]] = []
        for task_id in request.failed_task_ids:
            result = request.task_results.get(task_id)
            failed.append(
                {
                    "task_id": task_id,
                    "error_code": result.error.code if result and result.error else None,
                    "retryable": bool(result and result.error and result.error.retryable),
                }
            )
        return {
            "operation": "replan",
            "base_plan": {
                "plan_id": request.plan.plan_id,
                "tasks": self._task_summary(request.plan),
            },
            "failed_tasks": failed,
            "replan_reason": request.reason_code,
            "budget": request.plan.budget.model_dump(mode="json"),
            "allowed_actions": catalog.prompt_payload(),
        }
