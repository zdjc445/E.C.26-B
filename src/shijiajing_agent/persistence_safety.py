"""持久化边界脱敏。

Checkpoint 和 Cache 只能保存可恢复所需的结构化结果，不能把原始请求、图片内容或
用户自由 metadata 写入长期存储。该模块供 LangGraph native serializer 使用。
"""

from __future__ import annotations

import dataclasses
from typing import Any, cast

from pydantic import BaseModel

from shijiajing_agent.contracts import (
    AgentRequest,
    ConversationTurnSummary,
    ImageRef,
    RetrievalQuery,
    content_hash,
)

REDACTED_IMAGE_URI_PREFIX = "https://redacted.invalid/image/"

_SENSITIVE_MAPPING_KEYS = frozenset(
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


def redacted_image_uri(image: ImageRef) -> str:
    """返回只含摘要的不可访问图片占位引用。"""
    return f"{REDACTED_IMAGE_URI_PREFIX}{image.sha256}"


def is_redacted_image_ref(image: ImageRef | None) -> bool:
    """判断图片引用是否已经被持久化边界替换。"""
    return image is not None and image.uri.startswith(REDACTED_IMAGE_URI_PREFIX)


def _redact_image(image: ImageRef) -> ImageRef:
    return image.model_copy(update={"uri": redacted_image_uri(image)})


def _redact_request(request: AgentRequest) -> AgentRequest:
    metadata: dict[str, Any] = {
        key: request.metadata[key]
        for key in (
            "request_text_sha256",
            "request_text_length",
            "image_sha256",
            "image_id",
            "image_content_type",
        )
        if key in request.metadata
    }
    if request.text is not None:
        metadata["request_text_sha256"] = content_hash(request.text)
        metadata["request_text_length"] = len(request.text)
    if request.image is not None:
        metadata["image_sha256"] = request.image.sha256
        metadata["image_id"] = request.image.image_id
        metadata["image_content_type"] = request.image.content_type.value

    # model_copy 不重新执行 model_validator；这里显式清空原始输入，再用一个
    # 固定占位 selected_option_id 满足 AgentRequest 的“至少一项输入”不变量。
    return request.model_copy(
        update={
            "text": None,
            "image": _redact_image(request.image) if request.image is not None else None,
            "correction": None,
            "selected_option_id": request.selected_option_id or "__redacted_request__",
            "metadata": metadata,
        }
    )


def _redact_turn_summary(summary: ConversationTurnSummary) -> ConversationTurnSummary:
    if summary.user_text is None:
        return summary
    return summary.model_copy(
        update={
            "user_text": None,
            "user_text_sha256": content_hash(summary.user_text),
            "user_text_length": len(summary.user_text),
        }
    )


def _redact_query(query: RetrievalQuery) -> RetrievalQuery:
    """检索查询只保存结构化过滤结果；query_text 由当前请求重新构建。"""
    return query.model_copy(
        update={
            "query_text": "",
            "soft_terms": [],
            "negative_terms": [],
        }
    )


def sanitize_persisted_value(value: Any, *, drop_prompt: bool = False) -> Any:
    """递归清洗写入 Checkpoint 的值，同时保留领域模型类型。"""
    if isinstance(value, str) and value.lower().startswith(
        ("data:", "postgresql://", "postgres://", "sqlite://")
    ):
        return "<redacted>"
    if isinstance(value, AgentRequest):
        return _redact_request(value)
    if isinstance(value, ImageRef):
        return _redact_image(value)
    if isinstance(value, ConversationTurnSummary):
        return _redact_turn_summary(value)
    if isinstance(value, RetrievalQuery):
        return _redact_query(value)
    if isinstance(value, BaseModel):
        updates = {
            name: sanitize_persisted_value(getattr(value, name), drop_prompt=drop_prompt)
            for name in type(value).model_fields
        }
        return value.model_copy(update=updates)
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        fields = dataclasses.fields(value)
        updates = {
            field.name: sanitize_persisted_value(
                getattr(value, field.name), drop_prompt=drop_prompt
            )
            for field in fields
        }
        return dataclasses.replace(value, **updates)
    if isinstance(value, dict):
        mapping = cast(dict[Any, Any], value)
        result: dict[Any, Any] = {}
        for key, item in mapping.items():
            if isinstance(key, str) and (
                key.lower() in _SENSITIVE_MAPPING_KEYS or (drop_prompt and key.lower() == "prompt")
            ):
                continue
            result[key] = sanitize_persisted_value(item, drop_prompt=drop_prompt)
        return result
    if isinstance(value, (list, tuple)):
        sequence = cast(list[Any] | tuple[Any, ...], value)
        items = [sanitize_persisted_value(item, drop_prompt=drop_prompt) for item in sequence]
        return tuple(items) if isinstance(value, tuple) else items
    return value


def sanitize_cache_value(value: dict[str, Any], *, namespace: str | None = None) -> dict[str, Any]:
    """清洗 Cache JSON；只允许 explanation namespace 使用字段化解释文本。

    普通缓存的 ``text``/``prompt`` 是请求或 Prompt 自由文本，必须删除。解释缓存
    的载荷契约使用 ``explanation_text``，它是通过事实校验后的派生结果，不与普通
    输入字段共用名称。
    """
    safe = cast(dict[str, Any], sanitize_persisted_value(value, drop_prompt=True))
    if namespace != "explanation":
        safe.pop("explanation_text", None)
    if namespace == "explanation":
        explanation_text = safe.get("explanation_text")
        if (
            not isinstance(explanation_text, str)
            or not explanation_text
            or len(explanation_text) > 4000
        ):
            safe.pop("explanation_text", None)
    return safe
