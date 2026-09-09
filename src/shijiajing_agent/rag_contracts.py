"""RAG 运行时和索引发布使用的严格契约。

商品事实仍以 ``contracts.Offer`` 为唯一来源；本模块只承载查询计划、通道结果、
资格诊断和索引 manifest，避免把 RAG 过程状态塞进公共商品模型。
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from shijiajing_agent.agent_runtime.contracts import AgentRuntimeUsage
from shijiajing_agent.contracts import HardFilters, RetrievalCandidate


class QuerySource(StrEnum):
    ORIGINAL = "original"
    INITIAL_EXPANSION = "initial_expansion"
    SUPPLEMENT = "supplement"


class ChannelKind(StrEnum):
    DENSE = "dense"
    SPARSE = "sparse"
    IMAGE = "image"


class ChannelStatus(StrEnum):
    SUCCESS = "success"
    EMPTY = "empty"
    FAILED = "failed"
    UNAVAILABLE = "unavailable"


class RequirementState(StrEnum):
    SATISFIED = "satisfied"
    CONFLICT = "conflict"
    UNKNOWN = "unknown"


class SemanticRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirement_id: str = Field(min_length=1, max_length=128)
    user_text: str = Field(min_length=1, max_length=1000)
    field: str = Field(min_length=1, max_length=128)
    target_value: Any = None
    operator: Literal["eq", "not_eq", "in", "range", "contains"] = "eq"
    unit: str | None = Field(default=None, max_length=32)
    hard: bool = True
    source: str = Field(default="user", max_length=64)
    locked: bool = False


class PreparedQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query_id: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=2000)
    hard_filters: HardFilters = Field(default_factory=HardFilters)
    constraints_version: int = Field(ge=1)
    source: QuerySource
    requirement_ids: list[str] = Field(default_factory=list[str], max_length=20)
    assumptions: list[str] = Field(default_factory=list[str], max_length=20)
    evidence_refs: list[str] = Field(default_factory=list[str], max_length=20)
    fingerprint: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")


class QueryPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    original_query: PreparedQuery
    variants: list[PreparedQuery] = Field(default_factory=list[PreparedQuery], max_length=3)
    unresolved_ambiguities: list[str] = Field(default_factory=list[str], max_length=20)
    usage: AgentRuntimeUsage = Field(default_factory=AgentRuntimeUsage)


class ChannelResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query_id: str = Field(min_length=1, max_length=128)
    channel: ChannelKind
    hits: list[RetrievalCandidate] = Field(
        default_factory=list[RetrievalCandidate], max_length=1000
    )
    status: ChannelStatus
    truncated: bool = False
    usage: AgentRuntimeUsage = Field(default_factory=AgentRuntimeUsage)
    index_version: str | None = Field(default=None, max_length=128)


class RetrievalBatchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    channel_results: list[ChannelResult] = Field(default_factory=list[ChannelResult], max_length=20)
    offers: list[RetrievalCandidate] = Field(
        default_factory=list[RetrievalCandidate], max_length=1000
    )
    channel_health: dict[str, ChannelStatus] = Field(default_factory=dict[str, ChannelStatus])
    cache_hit: bool = False
    fallback_used: bool = False
    usage: AgentRuntimeUsage = Field(default_factory=AgentRuntimeUsage)


class RequirementMatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    offer_id: str = Field(min_length=1, max_length=256)
    requirement_id: str = Field(min_length=1, max_length=128)
    state: RequirementState
    evidence_refs: list[str] = Field(default_factory=list[str], max_length=20)
    adoption: str = Field(default="source_fact", max_length=64)
    reason: str = Field(min_length=1, max_length=256)


class CandidateAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_hits: int = Field(default=0, ge=0)
    unique_offers: int = Field(default=0, ge=0)
    selected_window: int = Field(default=0, ge=0, le=60)
    requirement_counts: dict[str, dict[RequirementState, int]] = Field(
        default_factory=dict[str, dict[RequirementState, int]]
    )
    comparable_groups: int = Field(default=0, ge=0)
    platform_count: int = Field(default=0, ge=0)
    product_concentration: float | None = Field(default=None, ge=0, le=1)
    unassessed: int = Field(default=0, ge=0)
    truncated: int = Field(default=0, ge=0)
    gaps: list[str] = Field(default_factory=list[str], max_length=50)
    query_assumptions: list[str] = Field(default_factory=list[str], max_length=50)


class IndexManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(min_length=1, max_length=64)
    snapshot_id: str = Field(min_length=1, max_length=128)
    source_batches: list[str] = Field(default_factory=list[str], max_length=1000)
    source_content_hash: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    text_generation_version: str = Field(min_length=1, max_length=64)
    tokenizer_version: str = Field(min_length=1, max_length=64)
    sparse_version: str = Field(min_length=1, max_length=64)
    embedding_model: str | None = Field(default=None, max_length=256)
    embedding_dimension: int | None = Field(default=None, gt=0)
    vector_normalization: str = Field(default="provider_defined", max_length=64)
    distance_metric: str = Field(min_length=1, max_length=32)
    collection: str | None = Field(default=None, max_length=256)
    built_at: datetime
    valid_offer_count: int = Field(ge=0)


__all__ = [
    "CandidateAssessment",
    "ChannelKind",
    "ChannelResult",
    "ChannelStatus",
    "IndexManifest",
    "PreparedQuery",
    "QueryPlan",
    "QuerySource",
    "RequirementMatch",
    "RequirementState",
    "RetrievalBatchResult",
    "SemanticRequirement",
]
