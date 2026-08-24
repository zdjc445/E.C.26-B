"""模型 Planner 专用契约。

这些类型刻意不复用 ``AgentTaskV2``。模型只能提出受 Supervisor 授权的动作，
真正的任务、输入、预算和授权引用由 Materializer 在进程内生成。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from shijiajing_agent.contracts import ExecutionPlan

PlannerActionKind = Literal["keep", "skip", "retry", "add_template"]


class PlannerAction(BaseModel):
    """模型可以选择的一个目录动作。"""

    model_config = ConfigDict(extra="forbid")

    action_id: str = Field(min_length=1, max_length=128)
    action: PlannerActionKind
    target_task_id: str | None = Field(default=None, min_length=1, max_length=128)
    template_id: str | None = Field(default=None, min_length=1, max_length=128)
    reason_code: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_.-]+$")

    @model_validator(mode="after")
    def _shape(self) -> PlannerAction:
        if self.action == "add_template" and not self.template_id:
            raise ValueError("add_template 必须携带 template_id")
        if self.action != "add_template" and self.template_id is not None:
            raise ValueError("非 add_template 动作不得携带 template_id")
        if self.action in {"skip", "retry", "add_template"} and not self.target_task_id:
            raise ValueError("该动作必须携带 target_task_id")
        return self


class PlannerProposal(BaseModel):
    """模型输出的最小结构化提议。"""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    base_plan_id: str = Field(min_length=1, max_length=128)
    actions: list[PlannerAction] = Field(default_factory=list[PlannerAction], max_length=64)


PlannerFallbackReason = Literal[
    "MODEL_DISABLED",
    "MODEL_TIMEOUT",
    "MODEL_NETWORK_ERROR",
    "MODEL_OUTPUT_INVALID",
    "ACTION_NOT_ALLOWED",
    "PLAN_MATERIALIZATION_FAILED",
    "PLAN_VALIDATION_FAILED",
    "BUDGET_EXCEEDED",
    "MODEL_PLAN_SHADOWED",
]


class PlanningOutcome(BaseModel):
    """一次 create/replan 的可恢复、可审计摘要；不包含模型原始响应。"""

    model_config = ConfigDict(extra="forbid")

    operation: Literal["create", "replan"]
    plan: ExecutionPlan
    source: Literal["model", "deterministic"]
    model_attempted: bool = False
    validated: bool = False
    accepted: bool = False
    fallback_reason: PlannerFallbackReason | None = None
    model: str | None = None
    prompt_version: str | None = None
    repair_count: int = Field(default=0, ge=0)
    duration_ms: float = Field(default=0.0, ge=0)
    proposal_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    candidate_plan_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    plan_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    token_usage: dict[str, int] = Field(default_factory=dict[str, int])
    action_count: int = Field(default=0, ge=0)
    task_count: int = Field(default=0, ge=0)
    attempt_id: str | None = Field(default=None, min_length=1, max_length=128)
