"""Workflow 层测试公共夹具：Fake Ports + mini taxonomy + Settings（方案 §21.3）。"""

from __future__ import annotations

from typing import Any

import pytest

from shijiajing_agent.config import Settings
from shijiajing_agent.contracts import (
    AgentEvent,
    HardFilters,
    ImageContentType,
    ImageRef,
    IntentPatch,
    Offer,
    RecognitionResult,
    RetrievalCandidate,
    RetrievalQuery,
    SellerType,
)
from shijiajing_agent.domain.filters import HardFilterBuilder
from shijiajing_agent.domain.intent_rules import RuleIntentParser
from shijiajing_agent.domain.taxonomy import Taxonomy, TaxonomyFile
from shijiajing_agent.errors import SessionConflictError
from shijiajing_agent.facade import AgentDependencies, AgentFacade
from shijiajing_agent.ports.retrieval import RetrievalResult
from shijiajing_agent.state import AgentState

# ---------------------------------------------------------------------------
# Fake Ports
# ---------------------------------------------------------------------------


class FakeVisionModel:
    """可配置结果/异常队列的 VLM；默认返回高置信识别结果。"""

    def __init__(self) -> None:
        self.calls = 0
        self.errors: list[Exception] = []
        self.results: list[RecognitionResult] = []

    async def setup(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def recognize(self, image: ImageRef, taxonomy: Taxonomy) -> RecognitionResult:
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)
        if self.results:
            return self.results.pop(0)
        return default_recognition()


class FakeIntentModel:
    """默认行为 = 规则解析器（与 §11.3 降级路径一致）；可注入异常/自定义 patch。"""

    def __init__(self, taxonomy: Taxonomy) -> None:
        self.calls = 0
        self.errors: list[Exception] = []
        self.results: list[IntentPatch] = []
        self._rules = RuleIntentParser(taxonomy)

    async def extract_intent(
        self, text: str, prev_constraints: Any, taxonomy: Taxonomy
    ) -> IntentPatch:
        self.calls += 1
        self.last_text = text
        if self.errors:
            raise self.errors.pop(0)
        if self.results:
            return self.results.pop(0)
        return self._rules.parse(text)


class FakeQueryRewrite:
    """默认回声确定性 base（与节点内的 HardFilterBuilder 同参数）。"""

    def __init__(self) -> None:
        self.calls = 0
        self.errors: list[Exception] = []
        self.results: list[RetrievalQuery] = []

    async def rewrite(
        self, text: str, constraints: Any, recognition: RecognitionResult | None
    ) -> RetrievalQuery:
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)
        if self.results:
            return self.results.pop(0)
        hf = HardFilterBuilder().build(constraints) if constraints else HardFilters()
        return RetrievalQuery(query_text=text or "", hard_filters=hf)


class FakeExplanation:
    """默认输出只包含证据中的数字（保证通过事实校验）。"""

    def __init__(self) -> None:
        self.calls = 0
        self.errors: list[Exception] = []
        self.results: list[str] = []

    async def explain(self, bundle: Any) -> str:
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)
        if self.results:
            return self.results.pop(0)
        if not bundle.groups:
            return "当前没有符合条件的比价结果。"
        g = bundle.groups[0]
        if g.min_price is not None:
            return f"为您找到同款商品，最低 {g.min_price:g} 元。"
        return "已为您找到同款商品。"


class FakeRetrieval:
    """可配置结果序列；空序列默认返回零结果。"""

    def __init__(self) -> None:
        self.calls = 0
        self.sequence: list[RetrievalResult | Exception] = []
        self.last_query: RetrievalQuery | None = None

    async def setup(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def search(
        self,
        query: RetrievalQuery,
        *,
        image: ImageRef | None = None,
        top_k: int = 100,
        union_limit: int = 200,
        category_names: dict[str, str] | None = None,
    ) -> RetrievalResult:
        self.calls += 1
        self.last_query = query
        if self.sequence:
            item = self.sequence.pop(0)
            if isinstance(item, Exception):
                raise item
            return item
        return RetrievalResult(candidates=[], total_found=0)


class FakeCheckpoint:
    """内存版 Checkpoint：乐观版本号 + 可注入冲突。"""

    def __init__(self) -> None:
        self.store: dict[str, tuple[AgentState, int]] = {}
        self.version = 0
        self.conflict_on_save = False
        self.resume_claims: set[tuple[str, str]] = set()

    async def setup(self) -> None:
        return None

    async def close(self) -> None:
        return None

    def seed(self, session_id: str, state: AgentState, version: int) -> None:
        self.version = max(self.version, version)
        self.store[session_id] = (dict(state), version)

    async def load(self, session_id: str) -> tuple[AgentState, int] | None:
        return self.store.get(session_id)

    async def save(self, session_id: str, state: AgentState, expected_version: int | None) -> int:
        if self.conflict_on_save:
            raise SessionConflictError("乐观版本冲突（注入）")
        prev = self.store.get(session_id)
        prev_version = prev[1] if prev else 0
        if expected_version is not None and prev_version != expected_version:
            raise SessionConflictError(
                f"乐观版本冲突：期望 {expected_version}，实际 {prev_version}"
            )
        self.version += 1
        # §17：state_version 由 Checkpoint 维护，随状态一起持久化
        state["state_version"] = self.version
        self.store[session_id] = (dict(state), self.version)
        return self.version

    async def claim_resume(self, session_id: str, interrupt_id: str) -> bool:
        key = (session_id, interrupt_id)
        if key in self.resume_claims:
            return False
        self.resume_claims.add(key)
        return True

    async def release_resume(self, session_id: str, interrupt_id: str) -> None:
        self.resume_claims.discard((session_id, interrupt_id))


class FakeTraceSink:
    def __init__(self) -> None:
        self.events: list[AgentEvent] = []

    async def setup(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def emit(self, event: AgentEvent) -> None:
        self.events.append(event)


class FakeMetrics:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}
        self.observations: list[tuple[str, float]] = []

    def inc(self, name: str, labels: dict[str, str] | None = None, value: float = 1.0) -> None:
        self.counts[name] = self.counts.get(name, 0) + int(value)

    def observe(self, name: str, value: float, labels: dict[str, str] | None = None) -> None:
        self.observations.append((name, value))


# ---------------------------------------------------------------------------
# 数据工厂
# ---------------------------------------------------------------------------


def default_recognition() -> RecognitionResult:
    return RecognitionResult(
        recognition_id="rec-1",
        category_id="headphone",
        category_name="耳机",
        brand="Sony",
        model="WH-1000XM5",
        keywords=["头戴式", "降噪"],
        attributes={},
        field_confidences={"category_id": 0.95, "brand": 0.92, "model": 0.95},
        overall_confidence=0.93,
    )


def make_image() -> ImageRef:
    return ImageRef(
        image_id="img-1",
        uri="data:image/jpeg;base64,AA==",
        content_type=ImageContentType.JPEG,
        sha256="a" * 64,
    )


def make_offer(
    offer_id: str,
    *,
    platform: str = "taobao",
    price: float,
    color: str = "黑色",
    brand: str = "Sony",
    model: str = "WH-1000XM5",
    rating: float = 4.8,
    sales: float = 12000.0,
    seller_type: SellerType = SellerType.OFFICIAL,
) -> Offer:
    return Offer(
        offer_id=offer_id,
        platform=platform,
        source_product_id=f"sp-{offer_id}",
        shop_id=f"shop-{offer_id}",
        source_updated_at="2026-08-01T00:00:00Z",
        title=f"{brand} {model} 头戴式降噪耳机",
        category_id="headphone",
        brand=brand,
        model=model,
        same_item_key="k-wh1000xm5",
        identity_attributes={"connectivity": "蓝牙", "wearing_style": "头戴式"},
        variant_attributes={"color": color, "set_type": "单件"},
        price=price,
        coupon_amount=0.0,
        shipping_fee=0.0,
        seller_type=seller_type,
        rating=rating,
        sales=sales,
    )


def candidate(
    offer_id: str, *, price: float, platform: str = "taobao", **kwargs: Any
) -> RetrievalCandidate:
    offer = make_offer(offer_id, platform=platform, price=price, **kwargs)
    return RetrievalCandidate(
        offer=offer,
        dense_text_score=0.8,
        sparse_score=0.7,
        recall_score=0.85,
        channel_sources=["dense", "sparse"],
    )


def two_candidate_result() -> RetrievalResult:
    """黑色(taobao, 1899) + 黑色(jd, 1999) 同 SKU → 一个比价组。"""
    return RetrievalResult(
        candidates=[
            candidate("o-taobao", price=1899.0, platform="taobao"),
            candidate("o-jd", price=1999.0, platform="jd"),
        ],
        total_found=2,
        channel_counts={"dense": 2},
    )


def two_sku_result() -> RetrievalResult:
    """黑色 1899 与 白色 1799 → 两个 SKU 比价组。"""
    return RetrievalResult(
        candidates=[
            candidate("o-black", price=1899.0, platform="taobao", color="黑色"),
            candidate("o-white", price=1799.0, platform="jd", color="白色"),
        ],
        total_found=2,
        channel_counts={"dense": 2},
    )


# ---------------------------------------------------------------------------
# 夹具
# ---------------------------------------------------------------------------


@pytest.fixture
def taxonomy() -> Taxonomy:
    data = {
        "schema_version": "1.0",
        "taxonomy_version": "wf.1",
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
def settings() -> Settings:
    return Settings()


def make_deps(
    taxonomy: Taxonomy,
    settings: Settings,
    *,
    vision: FakeVisionModel | None = None,
    intent: FakeIntentModel | None = None,
    rewrite: FakeQueryRewrite | None = None,
    explanation: FakeExplanation | None = None,
    retrieval: FakeRetrieval | None = None,
    checkpoint: FakeCheckpoint | None = None,
    trace: FakeTraceSink | None = None,
    metrics: FakeMetrics | None = None,
) -> tuple[
    AgentDependencies,
    dict[
        str,
        FakeVisionModel
        | FakeIntentModel
        | FakeQueryRewrite
        | FakeExplanation
        | FakeRetrieval
        | FakeCheckpoint
        | FakeTraceSink
        | FakeMetrics,
    ],
]:
    """装配依赖并返回 (deps, 全部 fake 的可观测句柄)。"""
    fakes: dict[str, Any] = {
        "vision": vision or FakeVisionModel(),
        "intent": intent or FakeIntentModel(taxonomy),
        "rewrite": rewrite or FakeQueryRewrite(),
        "explanation": explanation or FakeExplanation(),
        "retrieval": retrieval or FakeRetrieval(),
        "checkpoint": checkpoint or FakeCheckpoint(),
        "trace": trace or FakeTraceSink(),
        "metrics": metrics or FakeMetrics(),
    }
    deps = AgentDependencies(
        taxonomy=taxonomy,
        settings=settings,
        vision=fakes["vision"],
        intent=fakes["intent"],
        query_rewrite=fakes["rewrite"],
        explanation=fakes["explanation"],
        retrieval=fakes["retrieval"],
        checkpoint=fakes["checkpoint"],
        trace=fakes["trace"],
        metrics=fakes["metrics"],
    )
    return deps, fakes


@pytest.fixture
def deps_factory(taxonomy: Taxonomy) -> Any:
    """返回 make_deps，测试内按需覆盖 fake 配置。"""

    def factory(
        settings: Settings | None = None, **overrides: Any
    ) -> tuple[AgentDependencies, dict[str, Any]]:
        return make_deps(taxonomy, settings or Settings(), **overrides)

    return factory


@pytest.fixture
def facade_factory() -> Any:
    """AgentFacade 工厂（每次新建图，避免跨测试状态污染）。"""

    def factory(deps: AgentDependencies) -> AgentFacade:
        return AgentFacade(deps)

    return factory
