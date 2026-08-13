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
from typing import Any, Literal

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
# 输入契约（§6.1 – §6.3）
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
    node_name: str | None = None
    status: NodeStatus | None = None
    duration_ms: float | None = None
    provider: str | None = None
    model: str | None = None
    input_hash: str | None = None
    output_hash: str | None = None
    retry_count: int | None = None
    fallback_used: bool | None = None
    candidate_count_in: int | None = None
    candidate_count_out: int | None = None
    error_code: str | None = None
    resumed: bool | None = None
    resumed_node: str | None = None


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
