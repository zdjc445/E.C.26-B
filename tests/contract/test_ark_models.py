"""Ark 模型适配器契约测试（方案 §21.2）。

覆盖：合法 JSON、Markdown 包裹 JSON、缺字段、额外字段、错误类型、
结构化修复循环（最多 max_model_repairs 次）、网络失败重试与错误转换、
Prompt 版本与调用元数据记录、QueryRewrite 硬过滤不被篡改、Explanation 纯文本。
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from shijiajing_agent.adapters.ark_models import (
    ArkExplanationModel,
    ArkIntentModel,
    ArkModelClient,
    ArkQueryRewrite,
    ArkVisionModel,
    ModelCallRecord,
    build_ark_models,
    load_prompt,
)
from shijiajing_agent.config import Settings
from shijiajing_agent.contracts import (
    ImageContentType,
    ImageRef,
    IntentPatch,
    RecognitionResult,
    RetrievalQuery,
    ShoppingConstraints,
    SourcedValue,
)
from shijiajing_agent.domain.evidence import EvidenceBundle
from shijiajing_agent.domain.filters import HardFilterBuilder
from shijiajing_agent.errors import ModelOutputInvalidError, VisionUnavailableError

VALID_VISION_JSON = """{
  "recognition_id": "rec-abc12345",
  "category_id": "headphone",
  "category_name": "耳机",
  "brand": "Sony",
  "model": "WH-1000XM5",
  "keywords": ["头戴式", "降噪"],
  "attributes": {"color": "黑色"},
  "field_confidences": {"brand": 0.95, "model": 0.9},
  "overall_confidence": 0.93,
  "visible_evidence": ["标题含 WH-1000XM5"],
  "unresolved_fields": []
}"""


def make_image() -> ImageRef:
    return ImageRef(
        image_id="img-contract-1",
        uri="data:image/jpeg;base64,AA==",
        content_type=ImageContentType.JPEG,
        sha256="b" * 64,
    )


async def test_vision_valid_json(taxonomy: Any, ark_client: Any, metrics: Any) -> None:
    client, server = ark_client([VALID_VISION_JSON], metrics=metrics)
    model = ArkVisionModel(client)
    result = await model.recognize(make_image(), taxonomy)

    assert isinstance(result, RecognitionResult)
    assert result.recognition_id == "rec-abc12345"
    assert result.brand == "Sony"
    assert result.model == "WH-1000XM5"
    assert result.category_id == "headphone"
    assert result.overall_confidence == 0.93
    # 一次调用成功即计入结构化输出成功率
    assert metrics.counts["model_structured_output_success_rate"] == 1
    assert "model_repair_count" not in metrics.counts
    # 请求体：多模态 content 含图片 data URI 与 taxonomy 摘要
    last_req = server.requests[0]
    content = last_req["messages"][1]["content"]
    assert content[0]["type"] == "image_url"
    assert "data:image/jpeg" in content[0]["image_url"]["url"]
    assert "headphone" in last_req["messages"][0]["content"]
    assert "PROMPT_VERSION" not in last_req["messages"][0]["content"]
    await client.close()


async def test_vision_markdown_wrapped_json(taxonomy: Any, ark_client: Any) -> None:
    wrapped = f"```json\n{VALID_VISION_JSON}\n```"
    client, _ = ark_client([wrapped])
    model = ArkVisionModel(client)
    result = await model.recognize(make_image(), taxonomy)
    assert result.brand == "Sony"
    await client.close()


async def test_vision_missing_field_repaired(taxonomy: Any, ark_client: Any, metrics: Any) -> None:
    """缺 recognition_id：第一次校验失败，修复轮输出合法 JSON（§11.1 修复循环）。"""
    invalid = '{"brand": "Sony", "overall_confidence": 0.9}'
    records: list[ModelCallRecord] = []
    client, server = ark_client(
        [invalid, VALID_VISION_JSON], metrics=metrics, on_call=records.append
    )
    model = ArkVisionModel(client)
    result = await model.recognize(make_image(), taxonomy)

    assert result.recognition_id == "rec-abc12345"
    # 修复轮请求包含上轮输出与错误摘要
    assert len(server.requests) == 2
    repair_messages = server.requests[1]["messages"]
    assert any(m["role"] == "assistant" for m in repair_messages)
    assert "recognition_id" in repair_messages[-1]["content"]
    assert metrics.counts["model_repair_count"] == 1
    assert metrics.counts["model_structured_output_success_rate"] == 1
    assert len(records) == 1
    assert records[0].repair_count == 1
    assert records[0].success is True
    assert records[0].node == "recognize_image"
    assert records[0].prompt_version == "v1"
    assert records[0].output_hash is not None
    assert records[0].token_usage is not None
    assert records[0].token_usage["total_tokens"] == 46
    await client.close()


async def test_vision_extra_field_rejected(taxonomy: Any, ark_client: Any) -> None:
    """额外字段触发 extra="forbid"，进入修复循环（§21.2 额外字段）。"""
    invalid = '{"recognition_id": "r1", "brand": "Sony", "bogus_field": "x"}'
    client, server = ark_client([invalid, VALID_VISION_JSON])
    model = ArkVisionModel(client)
    result = await model.recognize(make_image(), taxonomy)
    assert result.brand == "Sony"
    assert "Extra inputs are not permitted" in server.requests[1]["messages"][-1]["content"]
    await client.close()


async def test_vision_wrong_type_repaired(taxonomy: Any, ark_client: Any) -> None:
    """错误类型（brand 为数字）→ 校验失败 → 修复（§21.2 错误类型）。"""
    invalid = '{"recognition_id": "r1", "brand": 123}'
    client, _ = ark_client([invalid, VALID_VISION_JSON])
    model = ArkVisionModel(client)
    result = await model.recognize(make_image(), taxonomy)
    assert result.brand == "Sony"
    await client.close()


async def test_vision_plain_text_repair(taxonomy: Any, ark_client: Any) -> None:
    """模型直接输出自然语言（无 JSON）→ 解析失败 → 修复。"""
    client, _ = ark_client(["抱歉，我没法识别这张图片。", VALID_VISION_JSON])
    model = ArkVisionModel(client)
    result = await model.recognize(make_image(), taxonomy)
    assert result.brand == "Sony"
    await client.close()


async def test_vision_persistent_invalid_raises(
    taxonomy: Any, ark_client: Any, metrics: Any
) -> None:
    """连续 3 次非法 → 修复 2 次后抛 VisionUnavailableError，走节点降级（§11.1）。"""
    bad = '{"brand": 123}'
    client, server = ark_client([bad, bad, bad], metrics=metrics)
    model = ArkVisionModel(client)
    with pytest.raises(VisionUnavailableError) as exc_info:
        await model.recognize(make_image(), taxonomy)
    assert "修复" in str(exc_info.value)
    assert len(server.requests) == 3  # 1 次初始 + 2 次修复
    assert metrics.counts["model_repair_count"] == 2
    assert "model_structured_output_success_rate" not in metrics.counts
    await client.close()


async def test_vision_network_error_retried_then_success(taxonomy: Any, ark_client: Any) -> None:
    """网络失败重试（max_network_attempts=2）：第一次抛连接错误，第二次成功。"""
    client, _ = ark_client([httpx.ConnectError("conn refused"), VALID_VISION_JSON])
    model = ArkVisionModel(client)
    result = await model.recognize(make_image(), taxonomy)
    assert result.brand == "Sony"
    await client.close()


async def test_vision_network_error_converted_to_vision_unavailable(
    taxonomy: Any, ark_client: Any, metrics: Any
) -> None:
    """网络持续失败 → VisionUnavailableError（§21.2 错误类型），并记录失败元数据。"""
    records: list[ModelCallRecord] = []
    client, server = ark_client(
        [httpx.ConnectError("conn refused"), httpx.ConnectError("conn refused")],
        metrics=metrics,
        on_call=records.append,
    )
    model = ArkVisionModel(client)
    with pytest.raises(VisionUnavailableError):
        await model.recognize(make_image(), taxonomy)
    assert len(server.requests) == 2  # 恰好重试 max_network_attempts=2 次，无 SDK 内部重试叠加
    assert len(records) == 1
    assert records[0].success is False
    assert records[0].attempts == 2
    assert "model_structured_output_success_rate" not in metrics.counts
    await client.close()


async def test_vision_http_error_converted(taxonomy: Any, ark_client: Any) -> None:
    """HTTP 5xx → 重试耗尽 → VisionUnavailableError。"""
    client, _ = ark_client([(500, "server error"), (500, "server error")])
    model = ArkVisionModel(client)
    with pytest.raises(VisionUnavailableError):
        await model.recognize(make_image(), taxonomy)
    await client.close()


async def test_intent_valid(taxonomy: Any, ark_client: Any) -> None:
    intent_json = """{
      "category_id": "headphone",
      "category_name": "耳机",
      "brand": "Sony",
      "max_price": 2000,
      "platforms": ["jd"],
      "sort_by": "price_asc",
      "preferences": ["official_store"],
      "attributes": {"color": "黑色"}
    }"""
    client, server = ark_client([intent_json])
    model = ArkIntentModel(client)
    patch = await model.extract_intent("黑色索尼耳机 2000以内 京东 最便宜", None, taxonomy)

    assert isinstance(patch, IntentPatch)
    assert patch.brand == "Sony"
    assert patch.max_price == 2000
    assert patch.platforms == ["jd"]
    assert patch.sort_by.value == "price_asc"
    assert patch.needs_clarification is False
    # prompt 注入 taxonomy 摘要（品牌别名 索尼→Sony）
    assert "索尼→Sony" in server.requests[0]["messages"][0]["content"]
    await client.close()


async def test_intent_persistent_invalid_raises(taxonomy: Any, ark_client: Any) -> None:
    """意图模型持续失败 → ModelOutputInvalidError（节点将走规则解析降级）。"""
    client, _ = ark_client(['{"brand": []}', '{"brand": []}', '{"brand": []}'])
    model = ArkIntentModel(client)
    with pytest.raises(ModelOutputInvalidError):
        await model.extract_intent("索尼耳机", None, taxonomy)
    await client.close()


async def test_rewrite_preserves_hard_filters(ark_client: Any, ark_settings: Any) -> None:
    """§11.4：改写只能动 query_text/soft_terms/negative_terms，硬过滤与确定性构建一致。"""
    rewrite_json = (
        '{"query_text": "Sony WH-1000XM5 头戴式", '
        '"soft_terms": ["降噪"], "negative_terms": ["线控"]}'
    )
    constraints = ShoppingConstraints(
        brand=SourcedValue(value="Sony", source="user_text"),
        category_id=SourcedValue(value="headphone", source="user_text"),
    )
    expected_hf = HardFilterBuilder(
        brand_confidence_threshold=ark_settings.brand_hard_filter_confidence,
        model_confidence_threshold=ark_settings.model_hard_filter_confidence,
    ).build(constraints)

    client, _ = ark_client([rewrite_json])
    model = ArkQueryRewrite(client)
    query = await model.rewrite("索尼 头戴式耳机 不要线控", constraints, None)

    assert isinstance(query, RetrievalQuery)
    assert query.query_text == "Sony WH-1000XM5 头戴式"
    assert query.soft_terms == ["降噪"]
    assert query.negative_terms == ["线控"]
    assert query.hard_filters == expected_hf  # 与节点内确定性构建逐字段一致
    await client.close()


async def test_rewrite_missing_output_uses_fallback_text(ark_client: Any) -> None:
    """模型未给 query_text 时回退用户原文。"""
    client, _ = ark_client(['{"soft_terms": []}'])
    model = ArkQueryRewrite(client)
    query = await model.rewrite("索尼耳机", None, None)
    assert query.query_text == "索尼耳机"
    await client.close()


async def test_rewrite_persistent_invalid_raises(ark_client: Any) -> None:
    client, _ = ark_client(['{"query_text": 42}', '{"query_text": 42}', '{"query_text": 42}'])
    model = ArkQueryRewrite(client)
    with pytest.raises(ModelOutputInvalidError):
        await model.rewrite("索尼耳机", None, None)
    await client.close()


async def test_explanation_plain_text(ark_client: Any) -> None:
    bundle = EvidenceBundle(
        query_summary="Sony WH-1000XM5 头戴式降噪耳机",
        groups=[],
        notices=["未找到符合条件的商品"],
    )
    client, _ = ark_client(["没有找到符合条件的同款商品，已为您尝试放宽品牌约束。"])
    model = ArkExplanationModel(client)
    text = await model.explain(bundle)
    assert "没有找到" in text
    assert "品牌" in text
    await client.close()


async def test_explanation_empty_output_raises(ark_client: Any) -> None:
    bundle = EvidenceBundle(query_summary="索尼耳机", groups=[])
    client, _ = ark_client([""])
    model = ArkExplanationModel(client)
    with pytest.raises(ModelOutputInvalidError):
        await model.explain(bundle)
    await client.close()


async def test_explanation_http_error_raises(ark_client: Any) -> None:
    bundle = EvidenceBundle(query_summary="索尼耳机", groups=[])
    client, _ = ark_client([(500, "boom"), (500, "boom")])
    model = ArkExplanationModel(client)
    with pytest.raises(ModelOutputInvalidError):
        await model.explain(bundle)
    await client.close()


async def test_missing_config_raises() -> None:
    """不硬编码密钥：配置缺失时启动即失败并列出精确缺失项。"""
    with pytest.raises(ValueError, match="ARK_API_KEY"):
        ArkModelClient(
            Settings(
                ark_base_url="https://x.example.local/v1",
                ark_vision_model="v",
                ark_text_model="t",
            )
        )


async def test_build_factory_returns_all_models(ark_settings: Settings) -> None:
    vision, intent, rewrite, explanation = build_ark_models(ark_settings)
    assert isinstance(vision, ArkVisionModel)
    assert isinstance(intent, ArkIntentModel)
    assert isinstance(rewrite, ArkQueryRewrite)
    assert isinstance(explanation, ArkExplanationModel)


async def test_prompt_versions_loaded() -> None:
    for name in ("vision.md", "intent.md", "query_rewrite.md", "explanation.md"):
        version, text = load_prompt(name)
        assert version == "v1"
        assert len(text) > 200
        assert "PROMPT_VERSION" not in text  # 版本行已剥离
    # taxonomy 摘要占位符只出现在需要 taxonomy 的两个 prompt 中
    assert "{{TAXONOMY_SUMMARY}}" in load_prompt("vision.md")[1]
    assert "{{TAXONOMY_SUMMARY}}" in load_prompt("intent.md")[1]
    assert "{{TAXONOMY_SUMMARY}}" not in load_prompt("query_rewrite.md")[1]
    assert "{{TAXONOMY_SUMMARY}}" not in load_prompt("explanation.md")[1]
