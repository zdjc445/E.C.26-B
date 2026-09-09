"""Reranker 白名单、响应校验和配置边界测试。"""

from __future__ import annotations

import httpx

from shijiajing_agent.adapters.reranker import AliyunRerankerAdapter
from shijiajing_agent.config import Settings
from shijiajing_agent.domain.reranker_summary import build_rerank_document, candidate_version
from shijiajing_agent.ports.reranker import RerankerStatus
from tests.unit.conftest import offer


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "reranker_base_url": "https://reranker.example/v1/reranks",
        "reranker_api_key": "secret-not-in-payload",
        "reranker_model": "qwen3-rerank",
    }
    values.update(overrides)
    return Settings(**values)


async def test_aliyun_reranker_sends_whitelisted_summary_and_validates_all_ids() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["json"] = request.read()
        return httpx.Response(
            200,
            json={
                "model": "qwen3-rerank-2026",
                "results": [
                    {"index": 1, "relevance_score": 0.9},
                    {"index": 0, "relevance_score": 0.2},
                ],
                "usage": {"total_tokens": 42},
            },
        )

    first = offer("o-1")
    first.source_payload_ref = "owner_id=private; api_key=secret"
    second = offer("o-2", variant={"switch": "red"})
    documents = [build_rerank_document(item).document for item in (first, second)]
    adapter = AliyunRerankerAdapter(_settings(), transport=httpx.MockTransport(handler))
    try:
        result = await adapter.rerank(
            "红轴耳机",
            documents,
            top_k=2,
            deadline=None,
            candidate_version=candidate_version([first, second]),
        )
    finally:
        await adapter.close()

    assert result.status is RerankerStatus.SUCCESS
    assert [item.offer_id for item in result.results] == ["o-2", "o-1"]
    assert result.usage.reranker_requests == 1
    body = seen["json"]
    assert isinstance(body, bytes)
    assert b"owner_id" not in body
    assert b"api_key" not in body
    assert b"secret-not-in-payload" not in body


async def test_aliyun_reranker_rejects_partial_or_duplicate_response() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": [
                    {"index": 0, "relevance_score": 0.9},
                    {"index": 0, "relevance_score": 0.8},
                ]
            },
        )

    items = [offer("o-1"), offer("o-2")]
    adapter = AliyunRerankerAdapter(_settings(), transport=httpx.MockTransport(handler))
    try:
        result = await adapter.rerank(
            "耳机",
            [build_rerank_document(item).document for item in items],
            top_k=2,
            deadline=None,
            candidate_version=candidate_version(items),
        )
    finally:
        await adapter.close()

    assert result.status is RerankerStatus.FAILED
    assert result.results == []
    assert result.fallback_reason == "invalid_result_score"


def test_summary_uses_sku_fields_and_does_not_send_business_or_private_fields() -> None:
    item = offer("o-1", variant={"switch": "red"})
    item.price = 1999
    item.shop_name = "seller@example.com"
    item.source_payload_ref = "/internal/raw/owner_id"
    summary = build_rerank_document(item).document

    assert "switch:red" in summary.text
    assert "1999" not in summary.text
    assert "seller@example.com" not in summary.text
    assert "/internal/raw" not in summary.text


def test_prod_requires_explicit_cloud_reranker_configuration() -> None:
    settings = Settings(env="prod", main_agent_model="main", checkpoint_dsn="checkpoint.db")
    missing = settings.validate(require_real_adapters=True)
    assert {"RERANKER_BASE_URL", "RERANKER_API_KEY", "RERANKER_MODEL"}.issubset(missing)
