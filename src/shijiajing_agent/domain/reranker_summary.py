"""精排输入的安全摘要和候选集身份。"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass

from shijiajing_agent.contracts import Offer
from shijiajing_agent.domain.raw_offer import RawAttributeScope
from shijiajing_agent.ports.reranker import RerankDocument, RerankTokenCounter

SUMMARY_VERSION = "offer-summary-v1"
INSTRUCTION_VERSION = "product-semantic-v1"
INSTRUCTION = (
    "Rank actual e-commerce SKU Offers by semantic relevance to the shopping request; "
    "distinguish SKU specifications, product-level options, and unrelated same-form terms."
)

_SENSITIVE = re.compile(
    r"(?:owner[_ -]?id|session[_ -]?id|request[_ -]?id|api[_ -]?key|bearer|password|secret|"
    r"credential|token\b|internal[/\\]|trace[/\\]|@[A-Za-z0-9.-]+\.[A-Za-z]{2,}|"
    r"(?:\+?\d[\d ()-]{7,}\d))",
    re.IGNORECASE,
)
_PRICE = re.compile(r"(?:[$￥¥€£]\s*\d[\d,.]*|\d[\d,.]*\s*(?:元|人民币|rmb|cny))", re.I)
_URL = re.compile(r"https?://\S+|www\.\S+", re.I)


class Utf8TokenCounter:
    """无外部模型文件时的保守估算器。

    它按 UTF-8 字节块估算而非按字符计数；生产部署应注入与已固定模型一致的
    tokenizer，并通过 ``version`` 写入精排身份。
    """

    version = "utf8-estimator-v1"

    def count(self, text: str) -> int:
        if not text:
            return 0
        return max(1, math.ceil(len(text.encode("utf-8")) / 4))

    def truncate(self, text: str, max_tokens: int) -> str:
        if max_tokens < 1:
            return ""
        if self.count(text) <= max_tokens:
            return text
        raw = text.encode("utf-8")[: max_tokens * 4]
        return raw.decode("utf-8", errors="ignore").rstrip()


@dataclass(frozen=True)
class RerankSummary:
    document: RerankDocument
    summary_version: str = SUMMARY_VERSION


def build_rerank_document(
    offer: Offer,
    *,
    max_tokens: int = 384,
    token_counter: RerankTokenCounter | None = None,
) -> RerankSummary:
    """按固定优先级生成只含白名单字段的 Offer 摘要。"""
    counter = token_counter or Utf8TokenCounter()
    if max_tokens < 1:
        raise ValueError("精排摘要 Token 上限必须大于 0")

    parts: list[str] = []

    def add(label: str, value: object, *, sanitize: bool = True) -> None:
        text = str(value).strip() if value is not None else ""
        if not text:
            return
        if sanitize:
            text = _safe_text(text)
        if text and not _SENSITIVE.search(text):
            parts.append(f"{label}: {text}")

    # 语义优先级固定：标题/类目 → 身份 → SKU 规格 → 商品/报价属性。
    add("title", offer.title)
    add("raw_category_path", offer.raw_category_path)
    add("brand", offer.brand)
    add("model", offer.model)
    for key, value in sorted(offer.identity_attributes.items()):
        add(f"SKU {key}", f"{key}:{value}")
    for key, value in sorted(offer.variant_attributes.items()):
        add(f"SKU {key}", f"{key}:{value}")
    for attribute in sorted(offer.raw_attributes, key=lambda item: item.attribute_id):
        if attribute.scope is RawAttributeScope.SKU:
            add("SKU raw", f"{attribute.raw_key}:{attribute.raw_value}")
    for key, value in sorted(offer.descriptive_attributes.items()):
        add(f"product/offer {key}", f"{key}:{value}")
    for attribute in sorted(offer.raw_attributes, key=lambda item: item.attribute_id):
        if attribute.scope in {RawAttributeScope.PRODUCT, RawAttributeScope.OFFER}:
            add(f"{attribute.scope.value} raw", f"{attribute.raw_key}:{attribute.raw_value}")

    selected: list[str] = []
    remaining = max_tokens
    truncated = False
    for part in parts:
        part_tokens = counter.count(part)
        if part_tokens <= remaining:
            selected.append(part)
            remaining -= part_tokens
            continue
        if remaining > 0:
            clipped = counter.truncate(part, remaining)
            if clipped:
                selected.append(clipped)
                truncated = True
        break
    text = "\n".join(selected).strip()
    if not text:
        raise ValueError("Offer 没有可发送的安全精排摘要")
    return RerankSummary(
        document=RerankDocument(
            offer_id=offer.offer_id,
            text=text,
            token_count=counter.count(text),
            truncated=truncated,
        )
    )


def candidate_version(offers: list[Offer]) -> str:
    """绑定候选集身份，覆盖 Offer 内容版本而不仅是 ID。"""
    payload = [
        {
            "offer_id": offer.offer_id,
            "source_content_hash": offer.source_content_hash,
            "source_revision": offer.source_revision,
            "data_version": offer.data_version,
            "search_text_hash": offer.search_text_hash,
        }
        for offer in sorted(offers, key=lambda item: item.offer_id)
    ]
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _safe_text(value: str) -> str:
    return _PRICE.sub("", _URL.sub("", value)).replace("\x00", " ").strip()


__all__ = [
    "INSTRUCTION",
    "INSTRUCTION_VERSION",
    "SUMMARY_VERSION",
    "RerankSummary",
    "Utf8TokenCounter",
    "build_rerank_document",
    "candidate_version",
]
