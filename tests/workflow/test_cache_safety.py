"""缓存载荷损坏时按 miss 处理，不改变节点业务结果。"""

from __future__ import annotations

from dataclasses import asdict, replace
from typing import Any

import pytest

from shijiajing_agent.adapters.cache import InMemoryVersionedCache
from shijiajing_agent.contracts import AgentRequest, RetrievalQuery
from shijiajing_agent.domain.cache_policy import safe_get, safe_set, versioned_key
from shijiajing_agent.domain.evidence import EvidenceBundle, GroupEvidence
from shijiajing_agent.nodes.intent_nodes import make_parse_intent_node
from shijiajing_agent.nodes.recognition_nodes import make_recognize_image_node
from shijiajing_agent.nodes.response_nodes import make_generate_explanation_node
from shijiajing_agent.nodes.retrieval_nodes import (
    make_retrieve_candidates_node,
    make_rewrite_query_node,
)

from .conftest import FakeMetrics, make_image, two_candidate_result


class BrokenCache:
    async def setup(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def get(self, namespace: str, key: str) -> dict[str, Any] | None:
        del namespace, key
        raise RuntimeError("cache get failed")

    async def set(self, namespace: str, key: str, value: dict[str, Any], ttl_seconds: int) -> None:
        del namespace, key, value, ttl_seconds
        raise RuntimeError("cache set failed")

    async def delete_namespace(self, namespace: str) -> None:
        del namespace
        raise RuntimeError("cache delete failed")


class RecordingCache:
    def __init__(self) -> None:
        self.inner = InMemoryVersionedCache()
        self.ttls: list[tuple[str, int]] = []

    async def setup(self) -> None:
        await self.inner.setup()

    async def close(self) -> None:
        await self.inner.close()

    async def get(self, namespace: str, key: str) -> dict[str, Any] | None:
        return await self.inner.get(namespace, key)

    async def set(self, namespace: str, key: str, value: dict[str, Any], ttl_seconds: int) -> None:
        self.ttls.append((namespace, ttl_seconds))
        await self.inner.set(namespace, key, value, ttl_seconds)

    async def delete_namespace(self, namespace: str) -> None:
        await self.inner.delete_namespace(namespace)


@pytest.mark.asyncio
async def test_cache_ttls_are_read_from_settings(deps_factory: Any) -> None:
    settings = replace(
        deps_factory()[0].settings,
        vision_cache_ttl_seconds=11,
        intent_cache_ttl_seconds=22,
        query_rewrite_cache_ttl_seconds=33,
        retrieval_cache_ttl_seconds=44,
        explanation_cache_ttl_seconds=55,
        retrieval_index_version="index-v1",
    )
    deps, fakes = deps_factory(settings)
    cache = RecordingCache()
    deps.cache = cache

    request = AgentRequest(session_id="s-ttl", request_id="r-ttl", text="索尼耳机")
    await make_recognize_image_node(deps)({"current_request": request, "image_ref": make_image()})
    await make_parse_intent_node(deps)(
        {"current_request": request, "effective_constraints": None, "notices": [], "fallbacks": []}
    )
    await make_rewrite_query_node(deps)(
        {
            "current_request": request,
            "effective_constraints": None,
            "recognition": None,
            "keywords": [],
            "dirty_flags": {"query_dirty": True},
            "notices": [],
            "fallbacks": [],
        }
    )
    fakes["retrieval"].sequence = [two_candidate_result()]
    await make_retrieve_candidates_node(deps)(
        {
            "current_request": request,
            "retrieval_query": RetrievalQuery(query_text="索尼耳机"),
            "image_ref": None,
            "dirty_flags": {"retrieval_dirty": True},
            "retrieval_attempts": 0,
            "notices": [],
            "fallbacks": [],
            "errors": [],
        }
    )
    bundle = EvidenceBundle(
        query_summary="耳机",
        groups=[
            GroupEvidence(
                group_id="g1",
                title="Sony 耳机",
                min_price=100.0,
                average_price=100.0,
                price_range="100",
                platform_names=["taobao"],
                match_confidence=0.9,
                offer_count=1,
                hit_conditions=[],
                missing_data=[],
                risks=[],
                rank=1,
            )
        ],
    )
    await make_generate_explanation_node(deps)(
        {
            "current_request": request,
            "turn_id": "t-ttl",
            "evidence_bundle": bundle,
            "notices": [],
            "fallbacks": [],
        }
    )

    assert cache.ttls == [
        ("vision", 11),
        ("intent", 22),
        ("query_rewrite", 33),
        ("retrieval", 44),
        ("explanation", 55),
    ]


@pytest.mark.asyncio
async def test_cache_failures_are_miss_safe_and_counted() -> None:
    metrics = FakeMetrics()
    cache = BrokenCache()

    assert await safe_get(cache, "intent", "k", metrics=metrics) is None
    await safe_set(cache, "intent", "k", {"value": 1}, 60, metrics=metrics)

    assert metrics.counts["cache_failure_total"] == 2


@pytest.mark.asyncio
async def test_malformed_intent_cache_calls_model(
    deps_factory: Any,
) -> None:
    deps, fakes = deps_factory()
    cache = InMemoryVersionedCache()
    deps.cache = cache
    request = AgentRequest(session_id="s-cache", request_id="r-intent", text="索尼耳机")
    key = versioned_key(
        {"text": request.text, "previous_constraints": None},
        {
            "model": deps.settings.ark_text_model,
            "prompt": "v1",
            "taxonomy": deps.taxonomy.taxonomy_version,
        },
    )
    await cache.set("intent", key, {"intent_patch": {"unexpected": object()}}, 60)

    result = await make_parse_intent_node(deps)(
        {"current_request": request, "effective_constraints": None, "notices": [], "fallbacks": []}
    )

    assert fakes["intent"].calls == 1
    assert result["intent_patch"].brand == "Sony"


@pytest.mark.asyncio
async def test_malformed_query_cache_calls_rewrite_model(
    deps_factory: Any,
) -> None:
    deps, fakes = deps_factory()
    cache = InMemoryVersionedCache()
    deps.cache = cache
    request = AgentRequest(session_id="s-cache", request_id="r-query", text="索尼耳机")
    key = versioned_key(
        {"text": request.text, "constraints": None, "recognition": None},
        {
            "model": deps.settings.ark_text_model,
            "prompt": "v1",
            "taxonomy": deps.taxonomy.taxonomy_version,
        },
    )
    await cache.set(
        "query_rewrite",
        key,
        {"retrieval_query": {"query_text": "缓存硬过滤", "hard_filters": {"category_id": "wrong"}}},
        60,
    )

    result = await make_rewrite_query_node(deps)(
        {
            "current_request": request,
            "effective_constraints": None,
            "recognition": None,
            "keywords": [],
            "dirty_flags": {"query_dirty": True},
            "notices": [],
            "fallbacks": [],
        }
    )

    assert fakes["rewrite"].calls == 1
    assert result["retrieval_query"] == RetrievalQuery(query_text="索尼耳机")


@pytest.mark.asyncio
async def test_malformed_retrieval_cache_calls_provider(
    deps_factory: Any,
    settings: Any,
) -> None:
    deps, fakes = deps_factory(replace(settings, retrieval_index_version="index-v1"))
    cache = InMemoryVersionedCache()
    deps.cache = cache
    request = AgentRequest(session_id="s-cache", request_id="r-retrieval", text="索尼耳机")
    query = RetrievalQuery(query_text="索尼耳机")
    key = versioned_key(
        {
            "query": query.model_dump(mode="json"),
            "image_sha256": None,
            "top_k": deps.settings.retrieval_top_k_per_channel,
            "union_limit": deps.settings.retrieval_union_limit,
        },
        {
            "index": deps.settings.retrieval_index_version,
            "fusion": deps.settings.retrieval_fusion_strategy,
            "rerank": None,
        },
    )
    await cache.set("retrieval", key, {"candidates": [{"not": "a candidate"}]}, 60)
    fakes["retrieval"].sequence = [two_candidate_result()]

    result = await make_retrieve_candidates_node(deps)(
        {
            "current_request": request,
            "retrieval_query": query,
            "image_ref": None,
            "dirty_flags": {"retrieval_dirty": True},
            "retrieval_attempts": 0,
            "notices": [],
            "fallbacks": [],
            "errors": [],
        }
    )

    assert fakes["retrieval"].calls == 1
    assert result["candidates"]


@pytest.mark.asyncio
async def test_unverified_explanation_cache_calls_model(
    deps_factory: Any,
) -> None:
    deps, fakes = deps_factory()
    cache = InMemoryVersionedCache()
    deps.cache = cache
    bundle = EvidenceBundle(
        query_summary="耳机",
        groups=[
            GroupEvidence(
                group_id="g1",
                title="Sony 耳机",
                min_price=100.0,
                average_price=100.0,
                price_range="100",
                platform_names=["taobao"],
                match_confidence=0.9,
                offer_count=1,
                hit_conditions=[],
                missing_data=[],
                risks=[],
                rank=1,
            )
        ],
    )
    key = versioned_key(
        {"evidence": asdict(bundle)},
        {"model": deps.settings.ark_text_model, "prompt": "v1"},
    )
    await cache.set("explanation", key, {"text": "最低 999 元", "verified": True}, 60)
    fakes["explanation"].results = ["最低 100 元"]

    result = await make_generate_explanation_node(deps)(
        {
            "current_request": AgentRequest(
                session_id="s-cache", request_id="r-explanation", text="索尼耳机"
            ),
            "turn_id": "t1",
            "evidence_bundle": bundle,
            "notices": [],
            "fallbacks": [],
        }
    )

    assert fakes["explanation"].calls == 1
    assert result["explanation_text"] == "最低 100 元"
    assert result["explanation_verified"] is True


@pytest.mark.asyncio
async def test_verified_explanation_cache_is_reused(
    deps_factory: Any,
) -> None:
    deps, fakes = deps_factory()
    cache = InMemoryVersionedCache()
    deps.cache = cache
    bundle = EvidenceBundle(
        query_summary="耳机",
        groups=[
            GroupEvidence(
                group_id="g1",
                title="Sony 耳机",
                min_price=100.0,
                average_price=100.0,
                price_range="100",
                platform_names=["taobao"],
                match_confidence=0.9,
                offer_count=1,
                hit_conditions=[],
                missing_data=[],
                risks=[],
                rank=1,
            )
        ],
    )
    key = versioned_key(
        {"evidence": asdict(bundle)},
        {"model": deps.settings.ark_text_model, "prompt": "v1"},
    )
    cached_text = "最低 100 元"
    await cache.set(
        "explanation",
        key,
        {"explanation_text": cached_text, "verified": True},
        60,
    )

    result = await make_generate_explanation_node(deps)(
        {
            "current_request": AgentRequest(
                session_id="s-cache", request_id="r-explanation-hit", text="索尼耳机"
            ),
            "turn_id": "t1",
            "evidence_bundle": bundle,
            "notices": [],
            "fallbacks": [],
        }
    )

    assert fakes["explanation"].calls == 0
    assert result["explanation_text"] == cached_text
    assert result["explanation_verified"] is True
