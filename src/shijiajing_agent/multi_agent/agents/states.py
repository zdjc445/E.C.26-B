"""Specialist 私有状态。

这些 TypedDict 只在单个 Agent invocation 内部使用，不能替代 SupervisorState，也不包含
其他 Agent 的输入或规范业务状态。
"""

from __future__ import annotations

from typing import TypedDict

from shijiajing_agent.contracts import (
    AgentTaskError,
    AgentTaskUsage,
    IntentPatch,
    MemoryMutation,
    MemoryRecord,
    NormalizedCandidate,
    RankedGroup,
    RecognitionResult,
    RetrievalCandidate,
    RetrievalQuery,
    SkuGroup,
)


class RecognitionAgentState(TypedDict, total=False):
    task_id: str
    image_id: str | None
    correction_applied: bool
    repair_count: int
    recognition: RecognitionResult | None
    error: AgentTaskError | None
    usage: AgentTaskUsage


class IntentAgentState(TypedDict, total=False):
    task_id: str
    text_length: int
    repair_count: int
    patch: IntentPatch | None
    error: AgentTaskError | None
    usage: AgentTaskUsage


class RetrievalAgentState(TypedDict, total=False):
    task_id: str
    query: RetrievalQuery | None
    candidates: list[RetrievalCandidate]
    normalized_candidates: list[NormalizedCandidate]
    spu_clusters: list[list[int]]
    sku_groups: list[SkuGroup]
    ranked_groups: list[RankedGroup]
    error: AgentTaskError | None
    usage: AgentTaskUsage


class ExplanationAgentState(TypedDict, total=False):
    task_id: str
    explanation_text: str
    verified: bool
    error: AgentTaskError | None
    usage: AgentTaskUsage


class MemoryAgentState(TypedDict, total=False):
    task_id: str
    operation: str
    records: list[MemoryRecord]
    mutations: list[MemoryMutation]
    committed: bool
    error: AgentTaskError | None
    usage: AgentTaskUsage
