"""契约测试公共夹具：录制响应的 FakeArkServer（OpenAI 兼容）+ 最小 taxonomy（方案 §21.2）。"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from typing import Any, NoReturn

import httpx
import pytest

from shijiajing_agent.adapters.ark_models import ArkModelClient
from shijiajing_agent.config import Settings
from shijiajing_agent.domain.taxonomy import Taxonomy, TaxonomyFile


class FakeArkServer:
    """OpenAI 兼容假服务：逐条弹出预录制响应。

    每个响应项可为：
    - ``str``：正常 chat completion 内容；
    - ``(status, message)``：HTTP 错误响应；
    - ``Exception`` 实例：直接抛给客户端（模拟网络故障）。
    """

    def __init__(self, responses: list[Any]) -> None:
        self._responses = list(responses)
        self.requests: list[dict[str, Any]] = []

    async def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.requests.append(body)
        if not self._responses:
            return _completion_response("")
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        if isinstance(item, tuple):
            status, message = item
            return httpx.Response(status, json={"error": {"message": message}})
        return _completion_response(item)


def _completion_response(content: str) -> httpx.Response:
    payload = {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 1755000000,
        "model": "test-model",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 12, "completion_tokens": 34, "total_tokens": 46},
    }
    return httpx.Response(200, json=payload)


def make_ark_settings(**overrides: Any) -> Settings:
    base: dict[str, Any] = {
        "ark_api_key": "test-key-not-hardcoded",
        "ark_base_url": "https://ark.example.local/v1",
        "ark_vision_model": "vision-test",
        "ark_text_model": "text-test",
    }
    base.update(overrides)
    return Settings(**base)


class FakeMetrics:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}
        self.observations: list[tuple[str, float]] = []

    def inc(self, name: str, labels: dict[str, str] | None = None, value: float = 1.0) -> None:
        self.counts[name] = self.counts.get(name, 0) + int(value)

    def observe(self, name: str, value: float, labels: dict[str, str] | None = None) -> None:
        self.observations.append((name, value))


def _skip_or_fail_postgres(message: str) -> NoReturn:
    """普通集成运行允许 skip；严格验收运行必须失败。"""

    if os.environ.get("SHIJIAJING_REQUIRE_POSTGRES") == "1":
        pytest.fail(message)
    pytest.skip(message)


@pytest.fixture
def taxonomy() -> Taxonomy:
    data = {
        "schema_version": "1.0",
        "taxonomy_version": "contract.1",
        "categories": [
            {
                "category_id": "headphone",
                "category_name": "耳机",
                "aliases": ["耳机", "蓝牙耳机"],
                "brand_aliases": {"索尼": "Sony"},
                "model_normalization_rules": {"uppercase": True},
                "searchable_attributes": ["noise_cancellation"],
                "identity_attributes": ["connectivity", "wearing_style"],
                "variant_attributes": ["color", "set_type"],
                "attribute_schema": {
                    "noise_cancellation": {"type": "string", "enum": ["主动降噪", "被动降噪"]},
                    "connectivity": {"type": "string", "enum": ["蓝牙", "有线"]},
                    "color": {"type": "string"},
                },
            }
        ],
        "unit_rules": [],
        "common_brand_aliases": {"索尼": "Sony"},
    }
    return Taxonomy(TaxonomyFile.model_validate(data))


@pytest.fixture
def ark_settings() -> Settings:
    return make_ark_settings()


@pytest.fixture
def metrics() -> FakeMetrics:
    return FakeMetrics()


@pytest.fixture(scope="session")
def postgres_dsn() -> Iterator[str]:
    dsn = os.environ.get("SHIJIAJING_TEST_POSTGRES_DSN")
    if dsn:
        yield dsn
        return

    # integration 模式下优先自动提供隔离数据库；普通测试不会创建容器。
    # Docker 不可用时必须明确 skip，不把环境问题伪装成 contract 通过。
    try:
        from testcontainers.community.postgres import PostgresContainer

        container: Any = PostgresContainer(
            image="postgres:16-alpine",
            username="shijiajing",
            password="shijiajing",
            dbname="shijiajing_test",
        )
        container.start()
    except Exception as exc:
        _skip_or_fail_postgres(
            "未设置 SHIJIAJING_TEST_POSTGRES_DSN，且 Testcontainers PostgreSQL 不可用："
            f"{type(exc).__name__}: {exc}"
        )

    try:
        yield container.get_connection_url(driver=None)
    finally:
        container.stop()


@pytest.fixture
def ark_client() -> Any:
    """ArkModelClient 工厂：注入 MockTransport + 可选的 metrics/on_call/配置覆盖。"""

    def factory(
        responses: list[Any],
        *,
        metrics: FakeMetrics | None = None,
        on_call: Any = None,
        **settings_overrides: Any,
    ) -> tuple[ArkModelClient, FakeArkServer]:
        server = FakeArkServer(responses)
        client = ArkModelClient(
            make_ark_settings(**settings_overrides),
            transport=httpx.MockTransport(server.handler),
            metrics=metrics,
            on_call=on_call,
        )
        return client, server

    return factory
