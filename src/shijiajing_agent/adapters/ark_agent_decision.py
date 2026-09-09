"""基于现有 ArkModelClient 的主 Agent 严格动作 JSON 适配器。"""

from __future__ import annotations

import json
from typing import Any, cast

from pydantic import BaseModel, ConfigDict

from shijiajing_agent.adapters.ark_models import (
    ArkModelClient,
    load_prompt,
    take_model_calls,
)
from shijiajing_agent.agent_runtime.contracts import (
    ActionKind,
    AgentRuntimeUsage,
    DecisionObservation,
    DecisionResult,
    MainAction,
    SubagentAction,
    SubagentActionKind,
    SubagentDecisionResult,
    SubagentObservation,
)
from shijiajing_agent.errors import ModelOutputInvalidError
from shijiajing_agent.ports.agent_decision import AgentDecisionPort, SubagentDecisionPort


class _DecisionEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: MainAction


class _SubagentDecisionEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: SubagentAction


class ArkAgentDecision(AgentDecisionPort):
    """适配器只返回动作和本次 usage，不从共享 ``last_call`` 取成本。"""

    def __init__(self, client: ArkModelClient, model: str) -> None:
        self._client = client
        self._model = model
        self._prompt_version, self._prompt = load_prompt("main_agent.md")

    async def decide(
        self,
        observation: DecisionObservation,
        allowed_actions: tuple[ActionKind, ...],
    ) -> DecisionResult:
        take_model_calls()
        try:
            obj = await self._client.structured_call(
                node="main_agent_decide",
                model=self._model,
                prompt_version=self._prompt_version,
                system_prompt=self._prompt,
                user_message=json.dumps(
                    observation.model_dump(mode="json"),
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                schema=_DecisionEnvelope,
                timeout_seconds=self._client.settings.text_model_timeout_seconds,
                repair_instruction=(
                    "动作必须是允许目录中的一个严格 JSON 对象；不能增加字段，"
                    "不能引用观察中不存在的 ID。"
                ),
                error_kind=ModelOutputInvalidError,
            )
        finally:
            calls = take_model_calls()
        envelope = _DecisionEnvelope.model_validate(obj)
        action = cast(Any, envelope.action)
        if action.kind not in allowed_actions:
            raise ModelOutputInvalidError(f"主 Agent 返回未授权动作: {action.kind.value}")
        usage = AgentRuntimeUsage(
            decisions=1,
            model_calls=len(calls),
            input_tokens=sum(
                int(item.token_usage.get("prompt_tokens", 0)) for item in calls if item.token_usage
            ),
            output_tokens=sum(
                int(item.token_usage.get("completion_tokens", 0))
                for item in calls
                if item.token_usage
            ),
        )
        return DecisionResult(
            action=cast(MainAction, action),
            usage=usage,
            model=self._model,
            prompt_version=self._prompt_version,
        )


class ArkSubagentDecision(SubagentDecisionPort):
    """Research/Verification 共用的严格子动作 JSON 适配器。"""

    def __init__(self, client: ArkModelClient, model: str, role: str) -> None:
        self._client = client
        self._model = model
        self._prompt_version, self._prompt = load_prompt(f"{role}_subagent.md")
        self._role = role

    async def decide(
        self,
        observation: SubagentObservation,
        allowed_actions: tuple[SubagentActionKind, ...],
    ) -> SubagentDecisionResult:
        take_model_calls()
        try:
            obj = await self._client.structured_call(
                node=f"{self._role}_subagent_decide",
                model=self._model,
                prompt_version=self._prompt_version,
                system_prompt=self._prompt,
                user_message=json.dumps(
                    observation.model_dump(mode="json"),
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                schema=_SubagentDecisionEnvelope,
                timeout_seconds=self._client.settings.text_model_timeout_seconds,
                repair_instruction=(
                    "动作必须在当前子任务的 allowed_actions 中；不能引用不存在的 ID，"
                    "不能添加字段或改变冻结约束。"
                ),
                error_kind=ModelOutputInvalidError,
            )
        finally:
            calls = take_model_calls()
        envelope = _SubagentDecisionEnvelope.model_validate(obj)
        action = envelope.action
        if action.kind not in allowed_actions:
            raise ModelOutputInvalidError(f"子 Agent 返回未授权动作: {action.kind.value}")
        usage = AgentRuntimeUsage(
            decisions=1,
            model_calls=len(calls),
            input_tokens=sum(
                int(item.token_usage.get("prompt_tokens", 0)) for item in calls if item.token_usage
            ),
            output_tokens=sum(
                int(item.token_usage.get("completion_tokens", 0))
                for item in calls
                if item.token_usage
            ),
        )
        return SubagentDecisionResult(
            action=action,
            usage=usage,
            model=self._model,
            prompt_version=self._prompt_version,
        )


__all__ = ["ArkAgentDecision", "ArkSubagentDecision"]
