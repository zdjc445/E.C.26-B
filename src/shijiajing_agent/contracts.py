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
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from shijiajing_agent.domain.raw_offer import (
    Availability,
    PriceBasis,
    Provenance,
    RawAttribute,
    RecordKind,
)

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

    @field_validator("scope_key")
    @classmethod
    def _scope_format(cls, value: str) -> str:
        if not _MEMORY_SCOPE_RE.fullmatch(value):
            raise ValueError("scope_key 只能是 global 或 category:<category_id>")
        return value


class MemoryQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope_keys: list[str] = Field(min_length=1)
    memory_keys: list[str] = Field(default_factory=list[str])
    limit: int = Field(ge=1, le=100)

    @field_validator("scope_keys")
    @classmethod
    def _scope_keys_are_bounded(cls, value: list[str]) -> list[str]:
        if (
            not value
            or len(value) > 3
            or any(not item or not _MEMORY_SCOPE_RE.fullmatch(item) for item in value)
        ):
            raise ValueError("scope_keys 只能包含 global 或 category:<category_id>")
        return list(dict.fromkeys(value))


class IgnoredMemoryRecord(BaseModel):
    """MemoryApplication 中的固定忽略原因，不包含记忆值。"""

    model_config = ConfigDict(extra="forbid")

    memory_id: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    reason_code: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_]+$")


class MemoryApplication(BaseModel):
    """一次 turn 对长期记忆的确定性应用结果。"""

    model_config = ConfigDict(extra="forbid")

    constraint_defaults: dict[str, Any] = Field(default_factory=dict[str, Any])
    ranking_priors: dict[str, Any] = Field(default_factory=dict[str, Any])
    negative_preferences: list[str] = Field(default_factory=list[str])
    applied_memory_ids: list[str] = Field(default_factory=list[str])
    ignored_records: list[IgnoredMemoryRecord] = Field(default_factory=list[IgnoredMemoryRecord])


class RankingContext(BaseModel):
    """检索/排序接收的长期记忆投影；不把记忆默认值混入硬过滤。"""

    model_config = ConfigDict(extra="forbid")

    memory_priors: dict[str, Any] = Field(default_factory=dict[str, Any])
    memory_negative_terms: list[str] = Field(default_factory=list[str])
    applied_memory_ids: list[str] = Field(default_factory=list[str])


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


class CanonicalUnderstanding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recognition: RecognitionResult | None = None
    intent_patch: IntentPatch | None = None
    constraints: ShoppingConstraints | None = None
    memory_records: list[MemoryRecord] = Field(default_factory=list[MemoryRecord])
    memory_application: MemoryApplication = Field(default_factory=MemoryApplication)


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
    source_sku_id: str | None = None
    source_offer_id: str | None = None
    record_kind: RecordKind = RecordKind.SKU_OFFER
    raw_category_path: str | None = Field(default=None, max_length=512)
    raw_attributes: list[RawAttribute] = Field(default_factory=list[RawAttribute], max_length=128)
    provenance: Provenance = Provenance.LEGACY_DERIVED
    source_revision: str | None = Field(default=None, max_length=128)
    source_content_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    availability: Availability = Availability.UNKNOWN
    price_basis: PriceBasis = PriceBasis.UNKNOWN
    source_updated_at: str | None = None
    data_version: str | None = None
    title: str = ""
    normalized_title: str | None = None
    search_text: str | None = None
    search_text_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
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


_DYNAMIC_KEY_RE = r"^[a-z][a-z0-9_]{0,63}$"
_DYNAMIC_SOURCE_PATH_RE = (
    r"^(title|category_id|brand|model|"
    r"identity_attributes\.[^\.\s]{1,128}|"
    r"variant_attributes\.[^\.\s]{1,128}|"
    r"descriptive_attributes\.[^\.\s]{1,128}|"
    r"raw_category_path|raw_attributes\.[^\.\s]{1,128}\.(raw_key|raw_value))$"
)


class EvidenceSpan(BaseModel):
    """动态商品模型结果所引用的同一 Offer 原文证据。"""

    model_config = ConfigDict(extra="forbid")

    offer_id: str = Field(min_length=1, max_length=256)
    source_path: str = Field(min_length=1, max_length=160, pattern=_DYNAMIC_SOURCE_PATH_RE)
    raw_value: str = Field(min_length=1, max_length=256)
    start: int | None = Field(default=None, ge=0)
    end: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _valid_span(self) -> EvidenceSpan:
        if self.start is not None and self.end is not None and self.end < self.start:
            raise ValueError("EvidenceSpan.end 不能小于 start")
        return self


class DynamicAttributeProposal(BaseModel):
    """当前候选窗口内发现的局部属性语义 proposal。"""

    model_config = ConfigDict(extra="forbid")

    canonical_key: str = Field(min_length=1, max_length=64, pattern=_DYNAMIC_KEY_RE)
    aliases: list[str] = Field(default_factory=list[str], max_length=32)
    role: Literal["identity", "variant", "descriptive"]
    value_kind: Literal["string", "number", "boolean"]
    unit_family: str | None = Field(default=None, max_length=64)
    role_confidence: float = Field(ge=0.0, le=1.0)
    support_offer_ids: list[str] = Field(default_factory=list[str], max_length=100)
    evidence: list[EvidenceSpan] = Field(default_factory=list[EvidenceSpan], max_length=100)


class DynamicConceptProposal(BaseModel):
    """局部商品概念及其属性 proposal。"""

    model_config = ConfigDict(extra="forbid")

    local_concept_id: str = Field(min_length=1, max_length=128)
    canonical_label: str = Field(min_length=1, max_length=256)
    label_confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[EvidenceSpan] = Field(default_factory=list[EvidenceSpan], max_length=100)
    attributes: list[DynamicAttributeProposal] = Field(
        default_factory=list[DynamicAttributeProposal], max_length=64
    )


class OfferConceptAssignment(BaseModel):
    """单条 Offer 到本次响应局部概念的关联。"""

    model_config = ConfigDict(extra="forbid")

    offer_id: str = Field(min_length=1, max_length=256)
    local_concept_id: str = Field(min_length=1, max_length=128)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[EvidenceSpan] = Field(default_factory=list[EvidenceSpan], max_length=32)


class DynamicSchemaProposal(BaseModel):
    """模型提出的请求级动态局部 Schema；未经领域校验不得直接使用。"""

    model_config = ConfigDict(extra="forbid")

    concepts: list[DynamicConceptProposal] = Field(
        default_factory=list[DynamicConceptProposal], max_length=16
    )
    assignments: list[OfferConceptAssignment] = Field(
        default_factory=list[OfferConceptAssignment], max_length=100
    )


class VerifiedDynamicAttribute(BaseModel):
    """通过证据、支持度和一致性校验后的动态属性。"""

    model_config = ConfigDict(extra="forbid")

    canonical_key: str = Field(min_length=1, max_length=64, pattern=_DYNAMIC_KEY_RE)
    aliases: list[str] = Field(default_factory=list[str], max_length=32)
    role: Literal["identity", "variant", "descriptive"]
    value_kind: Literal["string", "number", "boolean"]
    unit_family: str | None = Field(default=None, max_length=64)
    role_confidence: float = Field(ge=0.0, le=1.0)
    support_offer_ids: list[str] = Field(default_factory=list[str], max_length=100)
    evidence: list[EvidenceSpan] = Field(default_factory=list[EvidenceSpan], max_length=100)


class VerifiedDynamicConcept(BaseModel):
    """通过确定性复核后的动态商品概念。"""

    model_config = ConfigDict(extra="forbid")

    local_concept_id: str = Field(min_length=1, max_length=128)
    canonical_label: str = Field(min_length=1, max_length=256)
    label_confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[EvidenceSpan] = Field(default_factory=list[EvidenceSpan], max_length=100)
    attributes: list[VerifiedDynamicAttribute] = Field(
        default_factory=list[VerifiedDynamicAttribute], max_length=64
    )


class VerifiedDynamicSchema(BaseModel):
    """由服务端计算 schema_id 的、仅对当前候选窗口有效的 Schema。"""

    model_config = ConfigDict(extra="forbid")

    schema_id: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    concepts: list[VerifiedDynamicConcept] = Field(
        default_factory=list[VerifiedDynamicConcept], max_length=16
    )
    assignments: list[OfferConceptAssignment] = Field(
        default_factory=list[OfferConceptAssignment], max_length=100
    )
    input_offer_ids: list[str] = Field(default_factory=list[str], max_length=100)

    def concept_for_offer(self, offer_id: str) -> VerifiedDynamicConcept | None:
        assignment = next((a for a in self.assignments if a.offer_id == offer_id), None)
        if assignment is None:
            return None
        return next(
            (
                concept
                for concept in self.concepts
                if concept.local_concept_id == assignment.local_concept_id
            ),
            None,
        )

    def variant_keys_for_offer(self, offer_id: str) -> list[str]:
        concept = self.concept_for_offer(offer_id)
        if concept is None:
            return []
        return sorted(
            {
                attribute.canonical_key
                for attribute in concept.attributes
                if attribute.role == "variant"
            }
        )


class DynamicCanonicalField(BaseModel):
    """按已验证局部 Schema 提出的单个字段。"""

    model_config = ConfigDict(extra="forbid")

    canonical_key: str = Field(min_length=1, max_length=64, pattern=_DYNAMIC_KEY_RE)
    canonical_value: str = Field(min_length=1, max_length=256)
    role: Literal["identity", "variant", "descriptive"]
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: EvidenceSpan


class DynamicCanonicalizationItem(BaseModel):
    """按已验证动态 Schema 归一化的单条 Offer proposal。"""

    model_config = ConfigDict(extra="forbid")

    offer_id: str = Field(min_length=1, max_length=256)
    local_concept_id: str | None = Field(default=None, max_length=128)
    category_concept: str | None = Field(default=None, max_length=256)
    category_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    category_evidence: EvidenceSpan | None = None
    brand: str | None = Field(default=None, max_length=256)
    brand_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    brand_evidence: EvidenceSpan | None = None
    model: str | None = Field(default=None, max_length=256)
    model_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    model_evidence: EvidenceSpan | None = None
    fields: list[DynamicCanonicalField] = Field(
        default_factory=list[DynamicCanonicalField], max_length=128
    )
    unresolved_fields: list[str] = Field(default_factory=list[str], max_length=64)

    @model_validator(mode="after")
    def _unique_field_keys(self) -> DynamicCanonicalizationItem:
        keys = [field.canonical_key for field in self.fields]
        if len(keys) != len(set(keys)):
            raise ValueError("dynamic canonicalization 的 canonical_key 不能重复")
        return self


class DynamicCanonicalizationBatch(BaseModel):
    """动态商品归一化批次输出。"""

    model_config = ConfigDict(extra="forbid")

    schema_id: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    items: list[DynamicCanonicalizationItem] = Field(
        default_factory=list[DynamicCanonicalizationItem], max_length=100
    )

    @model_validator(mode="after")
    def _unique_offer_ids(self) -> DynamicCanonicalizationBatch:
        ids = [item.offer_id for item in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("dynamic canonicalization items 的 offer_id 不能重复")
        return self


class DynamicFieldStatus(StrEnum):
    ACCEPTED = "accepted"
    DESCRIPTIVE_ONLY = "descriptive_only"
    REJECTED = "rejected"
    UNRESOLVED = "unresolved"


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
    query_ids: list[str] = Field(default_factory=list[str], max_length=20)


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
    normalized_descriptive: dict[str, str] = Field(default_factory=dict[str, str])
    normalized_category_concept: str | None = None
    dynamic_category_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    dynamic_schema_id: str | None = Field(default=None, max_length=64)
    dynamic_variant_keys: list[str] = Field(default_factory=list[str], max_length=64)
    dynamic_field_statuses: dict[str, DynamicFieldStatus] = Field(
        default_factory=dict[str, DynamicFieldStatus]
    )
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
    subject_id: str | None = Field(default=None, max_length=128)
    category_id: str | None = Field(default=None, max_length=128)
    constraint_delta: dict[str, Any] = Field(default_factory=dict[str, Any])
    memory_effects: list[dict[str, str]] = Field(default_factory=list[dict[str, str]])
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
