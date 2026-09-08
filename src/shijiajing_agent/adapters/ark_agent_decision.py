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
)
from shijiajing_agent.errors import ModelOutputInvalidError
from shijiajing_agent.ports.agent_decision import AgentDecisionPort


class _DecisionEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: MainAction


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


__all__ = ["ArkAgentDecision"]
