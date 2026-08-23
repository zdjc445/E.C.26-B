"""对外协议：Agent 输入、输出、流式事件和领域数据结构。

本文档对应《识价镜 Agent 完整实现方案》第 6 节（对外契约）与第 7 节（领域模型）。
所有模型节点输出使用 Pydantic v2，设置 ``extra="forbid"``，先 JSON 解析、再类型校验、
再领域语义校验（见 ``domain/validation``）。
"""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# ---------------------------------------------------------------------------
# 基础枚举
# ---------------------------------------------------------------------------


class AgentStatus(StrEnum):
    SUCCESS = "success"
    CLARIFICATION = "clarification"
    NO_RESULTS = "no_results"
    FAILED = "failed"


class EventType(StrEnum):
    TURN_STARTED = "turn_started"
    NODE_STARTED = "node_started"
    NODE_COMPLETED = "node_completed"
    NODE_FALLBACK = "node_fallback"
    CLARIFICATION_READY = "clarification_ready"
    RESULTS_READY = "results_ready"
    TURN_FAILED = "turn_failed"


class ConstraintSource(StrEnum):
    USER_CORRECTION = "user_correction"
    USER_TEXT = "user_text"
    VISION = "vision"
    SELECTED_OPTION = "selected_option"
    MEMORY_EXPLICIT = "memory_explicit"
    DEFAULT = "default"


class SortBy(StrEnum):
    RECOMMENDED = "recommended"
    PRICE_ASC = "price_asc"
    PRICE_DESC = "price_desc"
    RATING_DESC = "rating_desc"
    SALES_DESC = "sales_desc"


class Preference(StrEnum):
    LOWEST_PRICE = "lowest_price"
    OFFICIAL_STORE = "official_store"
    FAST_DELIVERY = "fast_delivery"
    HIGH_RATING = "high_rating"
    HIGH_SALES = "high_sales"


class ImageContentType(StrEnum):
    JPEG = "image/jpeg"
    PNG = "image/png"
    WEBP = "image/webp"


class SellerType(StrEnum):
    OFFICIAL = "official"
    SELF_OPERATED = "self_operated"
    THIRD_PARTY = "third_party"
    UNKNOWN = "unknown"


class NodeStatus(StrEnum):
    SUCCESS = "success"
    FALLBACK = "fallback"
    FAILED = "failed"
    SKIPPED = "skipped"


class CompletionReason(StrEnum):
    SUCCESS = "success"
    CLARIFICATION = "clarification"
    NO_RESULTS = "no_results"
    FAILED = "failed"


# ---------------------------------------------------------------------------
# 输入契约。
# ---------------------------------------------------------------------------


def _is_private_host(host: str) -> bool:
    """回环、链路本地与 RFC 1918 内网地址不允许作为图片引用目标。"""
    if host in ("localhost", "::1", "0.0.0.0", "metadata.google.internal"):
        return True
    if host.endswith(".local"):
        return True
    if host.startswith("127.") or host.startswith("10.") or host.startswith("192.168."):
        return True
    if host.startswith("172."):
        try:
            return 16 <= int(host.split(".")[1]) <= 31
        except (IndexError, ValueError):
            return False
    return False


class ImageRef(BaseModel):
    """图片引用。Agent 不保存图片字节，只保存 image_id、sha256 和受控引用。"""

    model_config = ConfigDict(extra="forbid")

    image_id: str = Field(min_length=1, max_length=128)
    uri: str = Field(min_length=1, max_length=2048)
    content_type: ImageContentType
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("uri")
    @classmethod
    def _uri_scheme(cls, v: str) -> str:
        if v.startswith("data:"):
            return v
        from urllib.parse import urlparse

        parsed = urlparse(v)
        if parsed.scheme not in ("https", "http"):
            raise ValueError("uri 只允许受信任对象存储 URL 或 data URL")
        host = (parsed.hostname or "").lower()
        if _is_private_host(host):
            raise ValueError("uri 不允许指向内网、回环或本机地址")
        return v


class RecognitionCorrection(BaseModel):
    """用户修正。只允许作用于当前会话最新的 recognition_id。"""

    model_config = ConfigDict(extra="forbid")

    recognition_id: str = Field(min_length=1)
    category_id: str | None = None
    brand: str | None = None
    model: str | None = None
    attributes: dict[str, str | None] = Field(default_factory=dict[str, str | None])
    clear_fields: list[str] = Field(default_factory=list[str])


class AgentRequest(BaseModel):
    """单轮 Agent 输入。text、image、correction、selected_option_id 至少存在一项。"""

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1, max_length=128)
    request_id: str = Field(min_length=1, max_length=128)
    text: str | None = Field(default=None, max_length=4000)
    image: ImageRef | None = None
    correction: RecognitionCorrection | None = None
    selected_option_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict[str, Any])

    @field_validator("text")
    @classmethod
    def _strip_text(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        return v if v else None

    @model_validator(mode="after")
    def _at_least_one_input(self) -> AgentRequest:
        if not any((self.text, self.image, self.correction, self.selected_option_id)):
            raise ValueError("text、image、correction、selected_option_id 至少存在一项")
        return self


class AgentExecutionContext(BaseModel):
    """调用方可信上下文；memory_owner_id 不从普通请求 metadata 推断。"""

    model_config = ConfigDict(extra="forbid")

    memory_owner_id: str | None = Field(default=None, min_length=1, max_length=128)
    memory_enabled: bool = False


# ---------------------------------------------------------------------------
# 识别与意图输出（§11.2 – §11.3）
# ---------------------------------------------------------------------------


class RecognitionResult(BaseModel):
    """VLM 商品识别输出（模型结构化输出契约）。"""

    model_config = ConfigDict(extra="forbid")

    recognition_id: str = Field(min_length=1)
    category_id: str | None = None
    category_name: str | None = None
    brand: str | None = None
    model: str | None = None
    keywords: list[str] = Field(default_factory=list[str])
    attributes: dict[str, str] = Field(default_factory=dict[str, str])
    field_confidences: dict[str, float] = Field(default_factory=dict[str, float])
    overall_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    visible_evidence: list[str] = Field(default_factory=list[str])
    unresolved_fields: list[str] = Field(default_factory=list[str])


class MemoryOperation(StrEnum):
    UPSERT = "upsert"
    FORGET = "forget"
    CLEAR_OWNER = "clear_owner"


class MemoryApplyMode(StrEnum):
    CONSTRAINT_DEFAULT = "constraint_default"
    RANKING_PRIOR = "ranking_prior"
    NEGATIVE_PREFERENCE = "negative_preference"


class MemoryStatus(StrEnum):
    ACTIVE = "active"
    FORGOTTEN = "forgotten"


_MEMORY_SCOPE_RE = re.compile(r"^(global|category:[^:\s]+)$")


class MemoryDirective(BaseModel):
    """模型或调用方提出的显式长期记忆变更。"""

    model_config = ConfigDict(extra="forbid")

    operation: MemoryOperation
    memory_key: str | None = None
    value: Any = None
    scope_key: str = "global"
    apply_mode: MemoryApplyMode | None = None

    @field_validator("scope_key")
    @classmethod
    def _scope_format(cls, value: str) -> str:
        if not _MEMORY_SCOPE_RE.fullmatch(value):
            raise ValueError("scope_key 只能是 global 或 category:<category_id>")
        return value

    @model_validator(mode="after")
    def _operation_shape(self) -> MemoryDirective:
        has_key = self.memory_key is not None
        if self.operation is MemoryOperation.UPSERT:
            if not has_key or self.value is None or self.apply_mode is None:
                raise ValueError("UPSERT 必须提供 memory_key、value、apply_mode")
        elif self.operation is MemoryOperation.FORGET:
            if not has_key or self.value is not None or self.apply_mode is not None:
                raise ValueError("FORGET 只允许提供 memory_key")
        elif self.operation is MemoryOperation.CLEAR_OWNER:
            if (
                self.scope_key != "global"
                or has_key
                or self.value is not None
                or self.apply_mode is not None
            ):
                raise ValueError(
                    "CLEAR_OWNER 只能使用 global scope 且不能携带 key/value/apply_mode"
                )
        return self


class IntentPatch(BaseModel):
    """文本意图抽取输出。模型只输出当前轮 patch，不复制历史状态。

    用户没有提及的字段必须为 null。历史合并由 ConstraintMerger 完成。
    """

    model_config = ConfigDict(extra="forbid")

    category_id: str | None = None
    category_name: str | None = None
    brand: str | None = None
    model: str | None = None
    min_price: float | None = Field(default=None, ge=0)
    max_price: float | None = Field(default=None, ge=0)
    colors: list[str] | None = None
    platforms: list[str] | None = None
    min_rating: float | None = Field(default=None, ge=0, le=5)
    sort_by: SortBy | None = None
    preferences: list[Preference] | None = None
    cancelled_preferences: list[Preference] = Field(default_factory=list[Preference])
    attributes: dict[str, str | None] = Field(default_factory=dict[str, str | None])
    clear_fields: list[str] = Field(default_factory=list[str])
    keywords: list[str] = Field(default_factory=list[str])
    exclude_keywords: list[str] = Field(default_factory=list[str])
    needs_clarification: bool = False
    clarification_question: str | None = None
    negative_terms: list[str] = Field(default_factory=list[str])
    memory_directives: list[MemoryDirective] = Field(default_factory=list[MemoryDirective])


class MemoryRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    memory_id: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    memory_owner_id: str = Field(min_length=1, max_length=128)
    memory_key: str = Field(min_length=1)
    scope_key: str = Field(min_length=1)
    value: Any
    apply_mode: MemoryApplyMode
    confidence: float = Field(ge=0.0, le=1.0)
    status: MemoryStatus
    source_session_id: str = Field(min_length=1, max_length=128)
    source_request_id: str = Field(min_length=1, max_length=128)
    version: int = Field(ge=1)
    created_at: str = Field(min_length=1)
    updated_at: str = Field(min_length=1)
    expires_at: str | None = None


class MemoryQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope_keys: list[str] = Field(min_length=1)
    memory_keys: list[str] = Field(default_factory=list[str])
    limit: int = Field(ge=1, le=100)


class MemoryMutation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mutation_id: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    operation: MemoryOperation
    memory_key: str | None = None
    scope_key: str = "global"
    value: Any = None
    apply_mode: MemoryApplyMode | None = None
    source_session_id: str = Field(min_length=1, max_length=128)
    source_request_id: str = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def _same_shape_as_directive(self) -> MemoryMutation:
        MemoryDirective(
            operation=self.operation,
            memory_key=self.memory_key,
            value=self.value,
            scope_key=self.scope_key,
            apply_mode=self.apply_mode,
        )
        return self


class SpecialistAgentName(StrEnum):
    RECOGNITION = "recognition"
    INTENT = "intent"
    RETRIEVAL = "retrieval"
    EXPLANATION = "explanation"
    MEMORY = "memory"


class AgentTask(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1, max_length=128)
    request_id: str = Field(min_length=1, max_length=128)
    turn_id: str = Field(min_length=1)
    trace_id: str = Field(min_length=1)
    agent_name: SpecialistAgentName
    input_payload: dict[str, Any]
    memory_context: list[MemoryRecord] = Field(default_factory=list[MemoryRecord])


class AgentResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(min_length=1)
    agent_name: SpecialistAgentName
    status: NodeStatus
    output_payload: dict[str, Any] = Field(default_factory=dict[str, Any])
    evidence_refs: list[str] = Field(default_factory=list[str])
    proposed_memory_mutations: list[MemoryMutation] = Field(default_factory=list[MemoryMutation])
    notices: list[str] = Field(default_factory=list[str])


# ---------------------------------------------------------------------------
# 受控层级式 Multi-Agent 协议（schema 2.0）
# ---------------------------------------------------------------------------


class AgentTaskKind(StrEnum):
    """Supervisor 可派发的有限任务类型。"""

    RECOGNIZE = "recognition.recognize"
    APPLY_CORRECTION = "recognition.apply_correction"
    PARSE_INTENT = "intent.parse"
    RETRIEVE_AND_RANK = "retrieval.retrieve_and_rank"
    EXPLAIN = "explanation.explain"
    MEMORY_RECALL = "memory.recall"
    MEMORY_PREPARE = "memory.prepare"
    MEMORY_COMMIT = "memory.commit"


class AgentTaskBudget(BaseModel):
    """单个任务的资源上限；任务执行器不得自行扩大这些上限。"""

    model_config = ConfigDict(extra="forbid")

    max_seconds: float = Field(default=30.0, gt=0, le=3600)
    max_model_calls: int = Field(default=3, ge=0, le=100)
    max_tokens: int = Field(default=8192, ge=0, le=2_000_000)
    max_retries: int = Field(default=0, ge=0, le=10)


class AgentTaskError(BaseModel):
    """不泄漏供应商异常的固定任务错误。"""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=64, pattern=r"^[A-Z][A-Z0-9_]*$")
    message: str = Field(min_length=1, max_length=256)
    retryable: bool = False
    fallback: str | None = Field(default=None, max_length=64)


class AgentTaskUsage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_calls: int = Field(default=0, ge=0)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    duration_ms: float = Field(default=0.0, ge=0)
    retry_count: int = Field(default=0, ge=0)


class RecognitionTaskInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["recognition", "recognition.recognize", "recognition.apply_correction"] = (
        "recognition"
    )
    image: ImageRef | None = None
    correction: RecognitionCorrection | None = None
    previous_recognition: RecognitionResult | None = None
    taxonomy_version: str = Field(min_length=1)


class IntentTaskInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["intent", "intent.parse"] = "intent"
    text: str | None = Field(default=None, max_length=4000)
    previous_constraints: ShoppingConstraints | None = None
    recent_turns: list[ConversationTurnSummary] = Field(
        default_factory=lambda: list[ConversationTurnSummary]()
    )
    selected_option_id: str | None = None


class RetrievalTaskInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["retrieval", "retrieval.retrieve_and_rank"] = "retrieval"
    constraints: ShoppingConstraints
    recognition: RecognitionResult | None = None
    query_text: str = ""
    top_k: int = Field(default=100, ge=1, le=1000)
    union_limit: int = Field(default=200, ge=1, le=5000)
    index_version: str | None = None
    fusion_version: str | None = None
    rerank_version: str | None = None


class ExplanationTaskInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["explanation", "explanation.explain"] = "explanation"
    ranked_groups: list[RankedGroup] = Field(default_factory=lambda: list[RankedGroup]())
    evidence_bundle: Any | None = None
    constraints: ShoppingConstraints
    allowed_evidence_refs: list[str] = Field(default_factory=list[str])


class MemoryTaskInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["memory", "memory.recall", "memory.prepare", "memory.commit"] = "memory"
    operation: Literal["recall", "prepare", "commit"]
    session_id: str | None = None
    request_id: str | None = None
    memory_owner_id: str | None = Field(default=None, min_length=1, max_length=128)
    query: MemoryQuery | None = None
    directives: list[MemoryDirective] = Field(default_factory=list[MemoryDirective])
    mutations: list[MemoryMutation] = Field(default_factory=list[MemoryMutation])
    authorization_id: str | None = None


AgentTaskInput = Annotated[
    RecognitionTaskInput
    | IntentTaskInput
    | RetrievalTaskInput
    | ExplanationTaskInput
    | MemoryTaskInput,
    Field(discriminator="kind"),
]


class RecognitionTaskOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["recognition", "recognition.recognize", "recognition.apply_correction"] = (
        "recognition"
    )
    recognition: RecognitionResult | None = None
    review_recommended: bool = False
    fallback_reason: str | None = None


class IntentTaskOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["intent", "intent.parse"] = "intent"
    patch: IntentPatch | None = None
    missing_fields: list[str] = Field(default_factory=list[str])
    clarification_question: str | None = None


class RetrievalTaskOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["retrieval", "retrieval.retrieve_and_rank"] = "retrieval"
    query: RetrievalQuery | None = None
    candidates: list[RetrievalCandidate] = Field(default_factory=lambda: list[RetrievalCandidate]())
    normalized_candidates: list[NormalizedCandidate] = Field(
        default_factory=lambda: list[NormalizedCandidate]()
    )
    ranked_groups: list[RankedGroup] = Field(default_factory=lambda: list[RankedGroup]())
    fallback_used: bool = False
    relaxed_attributes: list[str] = Field(default_factory=list[str])


class ExplanationTaskOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["explanation", "explanation.explain"] = "explanation"
    explanation_text: str = Field(default="", max_length=4000)
    verified: bool = False
    evidence_refs: list[str] = Field(default_factory=list[str])
    fallback_reason: str | None = None


class MemoryTaskOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["memory", "memory.recall", "memory.prepare", "memory.commit"] = "memory"
    operation: Literal["recall", "prepare", "commit"]
    records: list[MemoryRecord] = Field(default_factory=list[MemoryRecord])
    mutations: list[MemoryMutation] = Field(default_factory=list[MemoryMutation])
    committed: bool = False
    saved: bool = False


AgentTaskOutput = Annotated[
    RecognitionTaskOutput
    | IntentTaskOutput
    | RetrievalTaskOutput
    | ExplanationTaskOutput
    | MemoryTaskOutput,
    Field(discriminator="kind"),
]


class HandoffRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_agent: SpecialistAgentName
    requested_task_kind: AgentTaskKind
    reason_code: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_.-]+$")
    input_refs: list[str] = Field(default_factory=list[str])


class AgentTaskV2(BaseModel):
    """2.0 任务协议；不包含通用 memory_context，按输入联合隔离数据。"""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["2.0"] = "2.0"
    plan_id: str = Field(min_length=1, max_length=128)
    task_id: str = Field(min_length=1, max_length=128)
    parent_task_id: str | None = None
    agent_name: SpecialistAgentName
    task_kind: AgentTaskKind
    depends_on: list[str] = Field(default_factory=list[str])
    attempt: int = Field(default=1, ge=1, le=100)
    idempotency_key: str = Field(min_length=1, max_length=256)
    deadline_at: str = Field(min_length=1, max_length=64)
    budget: AgentTaskBudget = Field(default_factory=AgentTaskBudget)
    input: AgentTaskInput

    @model_validator(mode="after")
    def _agent_and_input_match(self) -> AgentTaskV2:
        expected: dict[AgentTaskKind, SpecialistAgentName] = {
            AgentTaskKind.RECOGNIZE: SpecialistAgentName.RECOGNITION,
            AgentTaskKind.APPLY_CORRECTION: SpecialistAgentName.RECOGNITION,
            AgentTaskKind.PARSE_INTENT: SpecialistAgentName.INTENT,
            AgentTaskKind.RETRIEVE_AND_RANK: SpecialistAgentName.RETRIEVAL,
            AgentTaskKind.EXPLAIN: SpecialistAgentName.EXPLANATION,
            AgentTaskKind.MEMORY_RECALL: SpecialistAgentName.MEMORY,
            AgentTaskKind.MEMORY_PREPARE: SpecialistAgentName.MEMORY,
            AgentTaskKind.MEMORY_COMMIT: SpecialistAgentName.MEMORY,
        }
        if expected[self.task_kind] is not self.agent_name:
            raise ValueError("agent_name 与 task_kind 不匹配")
        input_name = {
            SpecialistAgentName.RECOGNITION: "recognition",
            SpecialistAgentName.INTENT: "intent",
            SpecialistAgentName.RETRIEVAL: "retrieval",
            SpecialistAgentName.EXPLANATION: "explanation",
            SpecialistAgentName.MEMORY: "memory",
        }[self.agent_name]
        if not str(getattr(self.input, "kind", "")).startswith(input_name):
            raise ValueError("任务 input discriminator 与 agent_name 不匹配")
        if self.task_kind is AgentTaskKind.MEMORY_RECALL and not (
            isinstance(self.input, MemoryTaskInput) and self.input.operation == "recall"
        ):
            raise ValueError("memory.recall 必须使用 recall input")
        if self.task_kind is AgentTaskKind.MEMORY_PREPARE and not (
            isinstance(self.input, MemoryTaskInput) and self.input.operation == "prepare"
        ):
            raise ValueError("memory.prepare 必须使用 prepare input")
        if self.task_kind is AgentTaskKind.MEMORY_COMMIT and not (
            isinstance(self.input, MemoryTaskInput) and self.input.operation == "commit"
        ):
            raise ValueError("memory.commit 必须使用 commit input")
        if self.task_kind is AgentTaskKind.RECOGNIZE and isinstance(
            self.input, RecognitionTaskInput
        ):
            if self.input.correction is not None:
                raise ValueError("recognition.recognize 不得携带 correction")
        if self.task_kind is AgentTaskKind.APPLY_CORRECTION and isinstance(
            self.input, RecognitionTaskInput
        ):
            if self.input.correction is None:
                raise ValueError("recognition.apply_correction 必须携带 correction")
        if len(set(self.depends_on)) != len(self.depends_on):
            raise ValueError("depends_on 不得重复")
        return self


class AgentResultV2(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["2.0"] = "2.0"
    plan_id: str = Field(min_length=1, max_length=128)
    task_id: str = Field(min_length=1, max_length=128)
    agent_name: SpecialistAgentName
    task_kind: AgentTaskKind
    status: NodeStatus
    output: AgentTaskOutput | None = None
    error: AgentTaskError | None = None
    evidence_refs: list[str] = Field(default_factory=list[str])
    handoff_requests: list[HandoffRequest] = Field(default_factory=list[HandoffRequest])
    proposed_memory_mutations: list[MemoryMutation] = Field(default_factory=list[MemoryMutation])
    usage: AgentTaskUsage = Field(default_factory=AgentTaskUsage)
    output_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def _validate_result(self) -> AgentResultV2:
        expected: dict[AgentTaskKind, SpecialistAgentName] = {
            AgentTaskKind.RECOGNIZE: SpecialistAgentName.RECOGNITION,
            AgentTaskKind.APPLY_CORRECTION: SpecialistAgentName.RECOGNITION,
            AgentTaskKind.PARSE_INTENT: SpecialistAgentName.INTENT,
            AgentTaskKind.RETRIEVE_AND_RANK: SpecialistAgentName.RETRIEVAL,
            AgentTaskKind.EXPLAIN: SpecialistAgentName.EXPLANATION,
            AgentTaskKind.MEMORY_RECALL: SpecialistAgentName.MEMORY,
            AgentTaskKind.MEMORY_PREPARE: SpecialistAgentName.MEMORY,
            AgentTaskKind.MEMORY_COMMIT: SpecialistAgentName.MEMORY,
        }
        if expected[self.task_kind] is not self.agent_name:
            raise ValueError("result agent_name 与 task_kind 不匹配")
        if self.status is NodeStatus.FAILED and self.error is None:
            raise ValueError("FAILED 结果必须携带 error")
        if self.status in {NodeStatus.SUCCESS, NodeStatus.FALLBACK} and self.output is None:
            raise ValueError("成功或降级结果必须携带 output")
        if self.output is not None:
            output_name = str(getattr(self.output, "kind", ""))
            agent_name = self.agent_name.value
            if not output_name.startswith(agent_name):
                raise ValueError("result output 类型与 agent_name 不匹配")
            if self.task_kind in {
                AgentTaskKind.RECOGNIZE,
                AgentTaskKind.APPLY_CORRECTION,
            } and not isinstance(self.output, RecognitionTaskOutput):
                raise ValueError("recognition task 必须返回 RecognitionTaskOutput")
            if self.task_kind is AgentTaskKind.PARSE_INTENT and not isinstance(
                self.output, IntentTaskOutput
            ):
                raise ValueError("intent task 必须返回 IntentTaskOutput")
            if self.task_kind is AgentTaskKind.RETRIEVE_AND_RANK and not isinstance(
                self.output, RetrievalTaskOutput
            ):
                raise ValueError("retrieval task 必须返回 RetrievalTaskOutput")
            if self.task_kind is AgentTaskKind.EXPLAIN and not isinstance(
                self.output, ExplanationTaskOutput
            ):
                raise ValueError("explanation task 必须返回 ExplanationTaskOutput")
            if self.task_kind in {
                AgentTaskKind.MEMORY_RECALL,
                AgentTaskKind.MEMORY_PREPARE,
                AgentTaskKind.MEMORY_COMMIT,
            }:
                if not isinstance(self.output, MemoryTaskOutput):
                    raise ValueError("memory task 必须返回 MemoryTaskOutput")
                expected_operation = {
                    AgentTaskKind.MEMORY_RECALL: "recall",
                    AgentTaskKind.MEMORY_PREPARE: "prepare",
                    AgentTaskKind.MEMORY_COMMIT: "commit",
                }[self.task_kind]
                if self.output.operation != expected_operation:
                    raise ValueError("memory output operation 与 task_kind 不匹配")
        if self.task_kind is AgentTaskKind.MEMORY_COMMIT and self.status is NodeStatus.SUCCESS:
            if not isinstance(self.output, MemoryTaskOutput) or not self.output.committed:
                raise ValueError("memory.commit 成功必须声明 committed")
        return self


class TaskRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task: AgentTaskV2
    status: NodeStatus = NodeStatus.SKIPPED
    result_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    started_at: str | None = None
    finished_at: str | None = None
    authorized: bool = False


class SupervisorBudgetUsage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_count: int = Field(default=0, ge=0)
    model_calls: int = Field(default=0, ge=0)
    tokens: int = Field(default=0, ge=0)
    elapsed_ms: float = Field(default=0.0, ge=0)
    replans: int = Field(default=0, ge=0)


class CanonicalUnderstanding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recognition: RecognitionResult | None = None
    intent_patch: IntentPatch | None = None
    constraints: ShoppingConstraints | None = None
    memory_records: list[MemoryRecord] = Field(default_factory=list[MemoryRecord])


class ExecutionPlan(BaseModel):
    """经确定性校验的任务 DAG。"""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["2.0"] = "2.0"
    plan_id: str = Field(min_length=1, max_length=128)
    tasks: list[AgentTaskV2] = Field(default_factory=list[AgentTaskV2])
    max_tasks: int = Field(default=32, ge=1, le=1000)
    max_replans: int = Field(default=2, ge=0, le=100)
    budget: AgentTaskBudget = Field(default_factory=lambda: AgentTaskBudget(max_seconds=60.0))

    @model_validator(mode="after")
    def _dag_is_valid(self) -> ExecutionPlan:
        task_ids = [task.task_id for task in self.tasks]
        if len(task_ids) != len(set(task_ids)):
            raise ValueError("ExecutionPlan task_id 必须唯一")
        if len(task_ids) > self.max_tasks:
            raise ValueError("ExecutionPlan 超出任务数预算")
        known = set(task_ids)
        for task in self.tasks:
            missing = set(task.depends_on) - known
            if missing:
                raise ValueError(f"ExecutionPlan 存在未知依赖: {sorted(missing)}")
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(task_id: str) -> None:
            if task_id in visiting:
                raise ValueError("ExecutionPlan 依赖图存在环")
            if task_id in visited:
                return
            visiting.add(task_id)
            task = next(item for item in self.tasks if item.task_id == task_id)
            for dependency in task.depends_on:
                visit(dependency)
            visiting.remove(task_id)
            visited.add(task_id)

        for task_id in task_ids:
            visit(task_id)
        return self


class SupervisorPlanningInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request: AgentRequest
    execution_context: AgentExecutionContext = Field(default_factory=AgentExecutionContext)
    taxonomy_version: str = Field(min_length=1)
    previous_plan_id: str | None = None


class SupervisorReplanningInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan: ExecutionPlan
    task_results: dict[str, AgentResultV2] = Field(default_factory=dict[str, AgentResultV2])
    failed_task_ids: list[str] = Field(default_factory=list[str])
    reason_code: str = Field(min_length=1, max_length=64)


class ExecutionPlanPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    skip_task_ids: list[str] = Field(default_factory=list[str])
    retry_task_ids: list[str] = Field(default_factory=list[str])
    add_tasks: list[AgentTaskV2] = Field(default_factory=list[AgentTaskV2])


# ---------------------------------------------------------------------------
# 约束（§7.1 – §7.2）
# ---------------------------------------------------------------------------


class SourcedValue(BaseModel):
    """带来源的约束值。"""

    model_config = ConfigDict(extra="forbid")

    value: Any = None
    source: ConstraintSource = ConstraintSource.DEFAULT
    confidence: float = 0.0
    updated_turn_id: str | None = None
    locked_by_user: bool = False


class ShoppingConstraints(BaseModel):
    """当前所有有效约束。字段固定为方案 §7.2 列表。"""

    model_config = ConfigDict(extra="forbid")

    category_id: SourcedValue = Field(default_factory=lambda: SourcedValue())
    category_name: SourcedValue = Field(default_factory=lambda: SourcedValue())
    brand: SourcedValue = Field(default_factory=lambda: SourcedValue())
    model: SourcedValue = Field(default_factory=lambda: SourcedValue())
    min_price: SourcedValue = Field(default_factory=lambda: SourcedValue())
    max_price: SourcedValue = Field(default_factory=lambda: SourcedValue())
    colors: SourcedValue = Field(default_factory=lambda: SourcedValue())
    platforms: SourcedValue = Field(default_factory=lambda: SourcedValue())
    min_rating: SourcedValue = Field(default_factory=lambda: SourcedValue())
    sort_by: SourcedValue = Field(default_factory=lambda: SourcedValue())
    preferences: SourcedValue = Field(default_factory=lambda: SourcedValue())
    attributes: SourcedValue = Field(default_factory=lambda: SourcedValue())
    clear_fields: list[str] = Field(default_factory=list[str])

    def effective_value(self, name: str) -> Any:
        sv = getattr(self, name)
        return sv.value if isinstance(sv, SourcedValue) else sv

    def is_user_locked(self, name: str) -> bool:
        sv = getattr(self, name)
        return isinstance(sv, SourcedValue) and sv.locked_by_user


# ---------------------------------------------------------------------------
# 检索（§13）
# ---------------------------------------------------------------------------


class HardFilters(BaseModel):
    """用户明确或高置信结构化约束，进入 Milvus filter，不得被模型改写。"""

    model_config = ConfigDict(extra="forbid")

    category_id: str | None = None
    min_price: float | None = None
    max_price: float | None = None
    platforms: list[str] = Field(default_factory=list[str])
    min_rating: float | None = None
    brand: str | None = None
    model: str | None = None


class RetrievalQuery(BaseModel):
    """混合召回查询。模型只能改写 query_text 和扩展 soft_terms，不得修改 hard_filters。"""

    model_config = ConfigDict(extra="forbid")

    query_text: str = ""
    hard_filters: HardFilters = Field(default_factory=HardFilters)
    soft_terms: list[str] = Field(default_factory=list[str])
    negative_terms: list[str] = Field(default_factory=list[str])


class RetrievalMode(StrEnum):
    TEXT = "text"
    IMAGE = "image"
    MIXED = "mixed"


class Offer(BaseModel):
    """Milvus Collection 中一条 Offer 记录（索引与比价的最小数据单元）。"""

    model_config = ConfigDict(extra="forbid")

    offer_id: str = Field(min_length=1)
    platform: str = Field(min_length=1)
    source_product_id: str | None = None
    source_updated_at: str | None = None
    data_version: str | None = None
    title: str = ""
    normalized_title: str | None = None
    search_text: str | None = None
    category_id: str | None = None
    brand: str | None = None
    model: str | None = None
    same_item_key: str | None = None
    sku_key: str | None = None
    identity_attributes: dict[str, str] = Field(default_factory=dict[str, str])
    variant_attributes: dict[str, str] = Field(default_factory=dict[str, str])
    descriptive_attributes: dict[str, str] = Field(default_factory=dict[str, str])
    price: float | None = None
    original_price: float | None = None
    shipping_fee: float | None = None
    coupon_amount: float | None = None
    currency: str = "CNY"
    shop_id: str | None = None
    shop_name: str | None = None
    seller_type: SellerType = SellerType.UNKNOWN
    rating: float | None = Field(default=None, ge=0, le=5)
    sales: float | None = Field(default=None, ge=0)
    review_count: float | None = Field(default=None, ge=0)
    delivery_days: float | None = Field(default=None, ge=0)
    source_payload_ref: str | None = None

    @field_validator("seller_type", mode="before")
    @classmethod
    def _seller_type_coerce(cls, v: Any) -> Any:
        if isinstance(v, str) and v not in {s.value for s in SellerType}:
            return SellerType.UNKNOWN
        return v


class RetrievalCandidate(BaseModel):
    """召回候选：Offer + 各通道分数 + 融合分。"""

    model_config = ConfigDict(extra="forbid")

    offer: Offer
    dense_text_score: float | None = None
    sparse_score: float | None = None
    image_similarity: float | None = None
    metadata_match: float = 0.0
    recall_score: float = 0.0
    rerank_score: float | None = None
    rerank_version: str | None = None
    channel_sources: list[str] = Field(default_factory=list[str])


# ---------------------------------------------------------------------------
# 同款 / SPU / SKU（§14）
# ---------------------------------------------------------------------------


class NormalizedCandidate(BaseModel):
    """字段标准化后的候选商品（§14.1 处理顺序第 2 步）。"""

    model_config = ConfigDict(extra="forbid")

    offer_id: str = Field(min_length=1)
    offer: Offer
    normalized_category_id: str | None = None
    normalized_brand: str | None = None
    normalized_model: str | None = None
    normalized_identity: dict[str, str] = Field(default_factory=dict[str, str])
    normalized_variant: dict[str, str] = Field(default_factory=dict[str, str])
    normalization_failures: list[str] = Field(default_factory=list[str])
    recall_score: float = 0.0


class MatchPair(BaseModel):
    """成对同款判定结果。"""

    model_config = ConfigDict(extra="forbid")

    offer_a_id: str = Field(min_length=1)
    offer_b_id: str = Field(min_length=1)
    same_item_score: float = Field(ge=0, le=1)
    title_similarity: float | None = None
    identity_overlap: float | None = None
    image_similarity: float | None = None
    source_key_signal: float = 0.0
    hard_conflicts: list[str] = Field(default_factory=list[str])
    verdict: Literal["same", "review", "different"] = "different"


class SkuGroup(BaseModel):
    """精确 SKU 比价组（§14.6 – §14.7）。"""

    model_config = ConfigDict(extra="forbid")

    group_id: str = Field(min_length=1)
    spu_id: str = Field(min_length=1)
    sku_signature: str | None = None
    sku_attributes: dict[str, str] = Field(default_factory=dict[str, str])
    offers: list[Offer] = Field(default_factory=list[Offer])
    min_price: float | None = None
    max_price: float | None = None
    average_price: float | None = None
    min_price_offer_id: str | None = None
    offer_count: int = 0
    platform_count: int = 0
    price_freshness: float | None = None
    match_confidence: float = 0.0
    missing_sku_attributes: list[str] = Field(default_factory=list[str])
    risks: list[str] = Field(default_factory=list[str])
    category_id: str | None = None
    category_name: str | None = None
    brand: str | None = None
    model: str | None = None
    title: str | None = None


# ---------------------------------------------------------------------------
# 澄清与响应（§16、§6.4）
# ---------------------------------------------------------------------------


class ClarificationOption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    option_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    applies_to: str | None = None


class Clarification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    reason_code: str = Field(min_length=1)
    missing_fields: list[str] = Field(default_factory=list[str])
    options: list[ClarificationOption] = Field(default_factory=list[ClarificationOption])
    subject_id: str | None = None
    turn_id: str | None = None


class RankedGroup(BaseModel):
    """排序完成的比价组（含证据与解释挂载点）。"""

    model_config = ConfigDict(extra="forbid")

    group: SkuGroup
    rank: int = 0
    ranking_score: float = 0.0
    intent_relevance: float = 0.0
    match_confidence: float = 0.0
    price_utility: float = 0.0
    seller_trust: float = 0.0
    rating_quality: float = 0.0
    sales_quality: float = 0.0
    freshness: float = 0.0
    missing_dimensions: list[str] = Field(default_factory=list[str])
    explanation: str | None = None
    explanation_verified: bool = False


class AgentResponse(BaseModel):
    """单轮最终响应（§6.4）。"""

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1)
    request_id: str = Field(min_length=1)
    turn_id: str = Field(min_length=1)
    status: AgentStatus
    message: str = ""
    recognition: RecognitionResult | None = None
    effective_constraints: ShoppingConstraints | None = None
    groups: list[RankedGroup] = Field(default_factory=list[RankedGroup])
    clarification: Clarification | None = None
    notices: list[str] = Field(default_factory=list[str])
    trace_id: str = Field(default="", min_length=1)


class InterruptKind(StrEnum):
    CLARIFICATION = "clarification"
    RECOGNITION_REVIEW = "recognition_review"
    SAME_ITEM_REVIEW = "same_item_review"
    MEMORY_CONFIRMATION = "memory_confirmation"


class AgentInterrupt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interrupt_id: str = Field(min_length=64, max_length=64)
    session_id: str = Field(min_length=1, max_length=128)
    request_id: str = Field(min_length=1, max_length=128)
    turn_id: str = Field(min_length=1)
    trace_id: str = Field(min_length=1)
    kind: InterruptKind
    prompt: str = Field(min_length=1, max_length=4000)
    payload: dict[str, Any] = Field(default_factory=dict[str, Any])


class AgentResume(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interrupt_id: str = Field(min_length=64, max_length=64)
    value: dict[str, Any] = Field(default_factory=dict[str, Any])


class ClarificationResume(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["select", "answer"]
    option_id: str | None = None
    text: str | None = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def _shape(self) -> ClarificationResume:
        if self.action == "select" and not self.option_id:
            raise ValueError("select 必须提供 option_id")
        if self.action == "answer" and not self.text:
            raise ValueError("answer 必须提供 text")
        return self


class RecognitionReviewResume(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["approve", "reject", "edit"]
    correction: RecognitionCorrection | None = None

    @model_validator(mode="after")
    def _shape(self) -> RecognitionReviewResume:
        if self.action == "edit" and self.correction is None:
            raise ValueError("edit 必须提供 correction")
        if self.action != "edit" and self.correction is not None:
            raise ValueError("approve/reject 不能携带 correction")
        return self


class SameItemReviewResume(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["accept", "split"]


class MemoryConfirmationResume(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["approve", "reject"]


class AgentTurnResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    response: AgentResponse | None = None
    interrupt: AgentInterrupt | None = None

    @model_validator(mode="after")
    def _exactly_one(self) -> AgentTurnResult:
        if (self.response is None) == (self.interrupt is None):
            raise ValueError("response 和 interrupt 必须恰好一个非空")
        return self


class ConversationTurnSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1, max_length=128)
    turn_id: str = Field(min_length=1)
    user_text: str | None = Field(default=None, max_length=4000)
    user_text_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    user_text_length: int | None = Field(default=None, ge=0, le=4000)
    intent_patch: IntentPatch | None = None
    completion_reason: CompletionReason | None = None
    selected_group_ids: list[str] = Field(default_factory=list[str])
    created_at: str = Field(min_length=1)


# ---------------------------------------------------------------------------
# 流式事件（§6.5）
# ---------------------------------------------------------------------------


class AgentEvent(BaseModel):
    """节点/回合事件。不输出模型思维链。"""

    model_config = ConfigDict(extra="forbid")

    session_id: str
    request_id: str
    turn_id: str
    trace_id: str
    event_type: EventType
    timestamp: str
    agent_name: str | None = None
    node_name: str | None = None
    status: NodeStatus | None = None
    duration_ms: float | None = None
    provider: str | None = None
    model: str | None = None
    prompt_version: str | None = None
    taxonomy_version: str | None = None
    retrieval_index_version: str | None = None
    fusion_version: str | None = None
    rerank_version: str | None = None
    token_usage: dict[str, int] | None = None
    cache_hit: bool | None = None
    interrupt_kind: str | None = None
    memory_operation_count: int | None = None
    checkpoint_migration: str | None = None
    input_hash: str | None = None
    output_hash: str | None = None
    retry_count: int | None = None
    fallback_used: bool | None = None
    candidate_count_in: int | None = None
    candidate_count_out: int | None = None
    error_code: str | None = None
    resumed: bool | None = None
    resumed_node: str | None = None


class AgentEventRecord(BaseModel):
    """追加式持久化事件；不保存完整用户文本、Prompt 或模型原始输出。"""

    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(min_length=64, max_length=64)
    session_id: str = Field(min_length=1, max_length=128)
    request_id: str = Field(min_length=1, max_length=128)
    turn_id: str = Field(min_length=1)
    trace_id: str = Field(min_length=1)
    agent_name: str = Field(min_length=1, max_length=64)
    node_name: str | None = Field(default=None, max_length=128)
    event_type: str = Field(min_length=1, max_length=64)
    status: str | None = Field(default=None, max_length=32)
    input_hash: str | None = None
    output_hash: str | None = None
    state_version: int | None = Field(default=None, ge=0)
    payload: dict[str, Any] = Field(default_factory=dict[str, Any])
    occurred_at: str = Field(min_length=1)

    @field_validator("payload")
    @classmethod
    def _payload_is_sanitized(cls, value: dict[str, Any]) -> dict[str, Any]:
        """事件只能携带白名单元数据，拒绝凭证、连接串和原始内容。"""

        forbidden_keys = frozenset(
            {
                "api_key",
                "ark_api_key",
                "cache_dsn",
                "checkpoint_dsn",
                "data_url",
                "dsn",
                "event_store_dsn",
                "image_uri",
                "memory_dsn",
                "password",
                "prompt",
                "prompt_text",
                "raw_prompt",
                "raw_response",
                "request_ledger_dsn",
                "secret",
                "text",
                "token",
                "trace_dsn",
                "user_text",
            }
        )

        def visit(item: Any, path: str) -> None:
            if isinstance(item, dict):
                for key, child in cast(dict[Any, Any], item).items():
                    key_text = str(key).lower()
                    child_path = f"{path}.{key_text}"
                    if key_text in forbidden_keys:
                        raise ValueError(f"事件 payload 禁止字段: {child_path}")
                    visit(child, child_path)
                return
            if isinstance(item, (list, tuple)):
                sequence = cast(list[Any] | tuple[Any, ...], item)
                for index, child in enumerate(sequence):
                    visit(child, f"{path}[{index}]")
                return
            if isinstance(item, str):
                lowered = item.lower()
                if lowered.startswith(("data:", "postgresql://", "postgres://", "sqlite://")):
                    raise ValueError(f"事件 payload 禁止原始资源内容: {path}")

        visit(value, "payload")
        return value


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------


def now_iso() -> str:
    """UTC ISO 时间戳。"""
    return datetime.now(UTC).isoformat()


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def content_hash(payload: Any) -> str:
    """对任意可 JSON 序列化对象计算稳定哈希（用于缓存键与输入哈希）。"""
    import json

    normalized = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def normalize_whitespace(text: str | None) -> str | None:
    if text is None:
        return None
    text = text.strip()
    text = re.sub(r"\s+", " ", text)
    return text if text else None
