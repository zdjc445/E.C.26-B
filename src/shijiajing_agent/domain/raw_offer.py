"""原始商品来源契约与确定性索引文本。

这一层只做来源结构的保真和边界控制，不把平台原字段猜测成全局商品语义。
``Offer`` 通过本模块的枚举和 ``RawAttribute`` 保存来源范围；标准化与资格判断
在比较阶段另行完成。
"""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from shijiajing_agent.contracts import Offer

_SAFE_ID_RE = r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}$"
_SHA256_RE = r"^[0-9a-f]{64}$"
_MAX_RAW_ATTRIBUTES = 128
_MAX_SEARCH_TEXT_BYTES = 16 * 1024


class RawAttributeScope(StrEnum):
    SKU = "sku"
    PRODUCT = "product"
    OFFER = "offer"
    UNKNOWN = "unknown"


class RecordKind(StrEnum):
    SKU_OFFER = "sku_offer"
    PRODUCT_SUMMARY = "product_summary"


class Provenance(StrEnum):
    SOURCE_NATIVE = "source_native"
    LEGACY_DERIVED = "legacy_derived"
    UNKNOWN = "unknown"


class Availability(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


class PriceBasis(StrEnum):
    SKU_LISTED = "sku_listed"
    PRODUCT_MINIMUM = "product_minimum"
    UNKNOWN = "unknown"


class RawAttribute(BaseModel):
    """来源记录中的一个原始属性；``source_locator`` 只用于追溯。"""

    model_config = ConfigDict(extra="forbid")

    attribute_id: str = Field(min_length=1, max_length=128, pattern=_SAFE_ID_RE)
    raw_key: str = Field(min_length=1, max_length=128)
    raw_value: str = Field(min_length=1, max_length=1024)
    scope: RawAttributeScope = RawAttributeScope.UNKNOWN
    source_locator: str | None = Field(default=None, max_length=512)
    source_value: Any = None


def build_offer_id(
    *,
    platform: str,
    source_offer_id: str | None = None,
    shop_id: str | None = None,
    source_product_id: str | None = None,
    source_sku_id: str | None = None,
) -> str:
    """根据来源身份生成无分隔符碰撞的稳定 Offer ID。"""

    identity = {
        "platform": platform,
        "source_offer_id": source_offer_id,
        "shop_id": shop_id,
        "source_product_id": source_product_id,
        "source_sku_id": source_sku_id,
    }
    if not any(identity[key] for key in identity if key != "platform"):
        raise ValueError("至少需要一个来源报价、卖家、商品或 SKU ID")
    encoded = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:40]
    return f"{platform}:offer:{digest}"


def source_content_hash(offer: Offer) -> str:
    """对来源事实做稳定哈希；生成文本本身不参与哈希，避免循环失效。"""

    payload = offer.model_dump(
        mode="json", exclude={"search_text", "search_text_hash", "source_content_hash"}
    )
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _truncate_utf8(text: str, limit: int = _MAX_SEARCH_TEXT_BYTES) -> str:
    data = text.encode("utf-8")
    if len(data) <= limit:
        return text
    return data[:limit].decode("utf-8", errors="ignore")


def build_raw_search_text(offer: Offer) -> str:
    """按固定顺序构造唯一的 Dense、Sparse 和本地 BM25 输入文本。"""

    parts: list[str] = []
    if offer.title:
        parts.append(f"title: {offer.title}")
    if offer.raw_category_path:
        parts.append(f"category: {offer.raw_category_path}")
    for attribute in sorted(offer.raw_attributes, key=lambda item: item.attribute_id):
        scope = attribute.scope.value
        parts.append(f"{scope}.{attribute.raw_key}: {attribute.raw_value}")
    # 历史快照的三个属性桶仍进入文本，但不改变其“legacy_derived”来源标记。
    for scope, attributes in (
        ("identity", offer.identity_attributes),
        ("variant", offer.variant_attributes),
        ("descriptive", offer.descriptive_attributes),
    ):
        for key, value in sorted(attributes.items()):
            parts.append(f"{scope}.{key}: {value}")
    if offer.brand:
        parts.append(f"brand: {offer.brand}")
    if offer.model:
        parts.append(f"model: {offer.model}")
    return _truncate_utf8("\n".join(parts))


def prepare_raw_offer(offer: Offer) -> Offer:
    """补齐确定性来源哈希和索引文本，不改写任何原始属性值。"""

    search_text = build_raw_search_text(offer)
    return offer.model_copy(
        update={
            "search_text": search_text,
            "search_text_hash": hashlib.sha256(search_text.encode("utf-8")).hexdigest(),
            "source_content_hash": offer.source_content_hash or source_content_hash(offer),
        }
    )


def raw_offer_from_mapping(payload: dict[str, Any]) -> Offer:
    """把平台原始映射转成 Offer；缺少 ``offer_id`` 时按来源身份派生。"""

    from shijiajing_agent.contracts import Offer

    values = dict(payload)
    if not values.get("offer_id"):
        values["offer_id"] = build_offer_id(
            platform=str(values.get("platform") or "unknown"),
            source_offer_id=values.get("source_offer_id"),
            shop_id=values.get("shop_id"),
            source_product_id=values.get("source_product_id"),
            source_sku_id=values.get("source_sku_id"),
        )
    return prepare_raw_offer(Offer.model_validate(values))


__all__ = [
    "Availability",
    "PriceBasis",
    "Provenance",
    "RawAttribute",
    "RawAttributeScope",
    "RecordKind",
    "build_offer_id",
    "build_raw_search_text",
    "prepare_raw_offer",
    "raw_offer_from_mapping",
    "source_content_hash",
]
