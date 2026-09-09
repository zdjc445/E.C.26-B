"""主 Agent 运行时及按需 subagent 的内部协议。"""

from shijiajing_agent.agent_runtime.contracts import (
    ActionKind,
    ActionRecord,
    AgentRuntimeUsage,
    DecisionObservation,
    DecisionResult,
    EvidenceQualityReport,
    EvidenceRecord,
    MainAction,
    RuntimeBudgetRemaining,
    SubagentResult,
    SubagentTask,
    SupplementQueryProposal,
    SupplementSearchAction,
    ToolObservation,
)

__all__ = [
    "ActionKind",
    "ActionRecord",
    "AgentRuntimeUsage",
    "DecisionObservation",
    "DecisionResult",
    "EvidenceQualityReport",
    "EvidenceRecord",
    "MainAction",
    "RuntimeBudgetRemaining",
    "SubagentResult",
    "SubagentTask",
    "SupplementQueryProposal",
    "SupplementSearchAction",
    "ToolObservation",
]
