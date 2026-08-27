"""专业子图返回根图前使用的严格输出契约。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from shijiajing_agent.contracts import (
    IntentPatch,
    MemoryApplication,
    MemoryMutation,
    MemoryRecord,
    NormalizedCandidate,
    RankingContext,
    RecognitionResult,
    RetrievalCandidate,
    RetrievalQuery,
)
from shijiajing_agent.domain.evidence import EvidenceBundle


class _SubgraphOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RecognitionSubgraphOutput(_SubgraphOutput):
    subject_id: str | None = None
    recognition: RecognitionResult | None = None
    recognition_history: list[RecognitionResult] = Field(default_factory=list[RecognitionResult])
    recognition_id: str | None = None
    keywords: list[str] = Field(default_factory=list[str])
    notices: list[str] = Field(default_factory=list[str])
    errors: list[dict[str, Any]] = Field(default_factory=list[dict[str, Any]])
    dirty_flags: dict[str, bool] = Field(default_factory=dict[str, bool])
    next_action: str | None = None
    node_events: list[dict[str, Any]] = Field(default_factory=list[dict[str, Any]])


class IntentSubgraphOutput(_SubgraphOutput):
    intent_patch: IntentPatch | None = None
    notices: list[str] = Field(default_factory=list[str])
    fallbacks: list[dict[str, Any]] = Field(default_factory=list[dict[str, Any]])
    next_action: str | None = None
    node_events: list[dict[str, Any]] = Field(default_factory=list[dict[str, Any]])


class RetrievalSubgraphOutput(_SubgraphOutput):
    retrieval_query: RetrievalQuery | None = None
    candidates: list[RetrievalCandidate] = Field(default_factory=list[RetrievalCandidate])
    retrieval_attempts: int = 0
    retrieval_fallback_used: bool = False
    relaxation_attempted: bool = False
    relaxed_attributes: list[str] = Field(default_factory=list[str])
    normalized_candidates: list[NormalizedCandidate] = Field(
        default_factory=list[NormalizedCandidate]
    )
    notices: list[str] = Field(default_factory=list[str])
    fallbacks: list[dict[str, Any]] = Field(default_factory=list[dict[str, Any]])
    errors: list[dict[str, Any]] = Field(default_factory=list[dict[str, Any]])
    dirty_flags: dict[str, bool] = Field(default_factory=dict[str, bool])
    next_action: str | None = None
    fusion_version: str | None = None
    rerank_version: str | None = None
    retrieval_index_version: str | None = None
    node_events: list[dict[str, Any]] = Field(default_factory=list[dict[str, Any]])


class ExplanationSubgraphOutput(_SubgraphOutput):
    evidence_bundle: EvidenceBundle | None = None
    explanation_text: str | None = None
    explanation_verified: bool = False
    notices: list[str] = Field(default_factory=list[str])
    fallbacks: list[dict[str, Any]] = Field(default_factory=list[dict[str, Any]])
    errors: list[dict[str, Any]] = Field(default_factory=list[dict[str, Any]])
    next_action: str | None = None
    node_events: list[dict[str, Any]] = Field(default_factory=list[dict[str, Any]])


class MemorySubgraphOutput(_SubgraphOutput):
    memory_context: list[MemoryRecord] = Field(default_factory=list[MemoryRecord])
    pending_memory_mutations: list[MemoryMutation] = Field(default_factory=list[MemoryMutation])
    memory_application: MemoryApplication = Field(default_factory=MemoryApplication)
    ranking_context: RankingContext = Field(default_factory=RankingContext)
    notices: list[str] = Field(default_factory=list[str])
    node_events: list[dict[str, Any]] = Field(default_factory=list[dict[str, Any]])


__all__ = [
    "ExplanationSubgraphOutput",
    "IntentSubgraphOutput",
    "MemorySubgraphOutput",
    "RecognitionSubgraphOutput",
    "RetrievalSubgraphOutput",
]
