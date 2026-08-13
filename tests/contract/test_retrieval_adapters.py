"""检索适配器契约测试（方案 §21.2）。

- Milvus Adapter：字段映射、filter 表达式、通道融合（§13.4 权重）、
  image 通道跳过、Milvus 失败 → 本地词法降级（§13.7）。
- Local Fallback 与 Milvus 返回相同领域协议（RetrievalResult / RetrievalCandidate）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from shijiajing_agent.adapters.embeddings import UnavailableImageEmbedding
from shijiajing_agent.adapters.local_retrieval import LocalLexicalRetrievalAdapter
from shijiajing_agent.adapters.milvus_retrieval import (
    MilvusHybridRetrievalAdapter,
    _entity_to_offer,
    build_filter_expr,
)
from shijiajing_agent.config import Settings
from shijiajing_agent.contracts import (
    HardFilters,
    ImageContentType,
    ImageRef,
    RetrievalQuery,
)
from shijiajing_agent.errors import RetrievalUnavailableError
from shijiajing_agent.ports.retrieval import RetrievalResult
from tests.unit.conftest import offer as make_offer

# ---------------------------------------------------------------------------
# Milvus filter 表达式（§13.5 / §21.2 字段映射与 filter 表达式）
# ---------------------------------------------------------------------------


def test_build_filter_expr_all_fields() -> None:
    hf = HardFilters(
        category_id="headphone",
        min_price=1000,
        max_price=2000,
        platforms=["jd", "taobao"],
        min_rating=4.5,
        brand="Sony",
        model="WH-1000XM5",
    )
    expr = build_filter_expr(hf)
    assert "category_id == 'headphone'" in expr
    assert "price >= 1000" in expr
    assert "price <= 2000" in expr
    assert "platform in ['jd', 'taobao']" in expr
    assert "rating >= 4.5" in expr
    assert "brand == 'Sony'" in expr
    assert "model == 'WH-1000XM5'" in expr
    assert expr.count(" && ") == 6


def test_build_filter_expr_empty() -> None:
    assert build_filter_expr(HardFilters()) == ""


def test_build_filter_expr_escapes_quotes() -> None:
    expr = build_filter_expr(HardFilters(brand="O'Brien's"))
    assert "'O\\'Brien\\'s'" in expr


def test_build_filter_expr_float_formatting() -> None:
    expr = build_filter_expr(HardFilters(min_price=1000.5, min_rating=4.8))
    assert "price >= 1000.5" in expr
    assert "rating >= 4.8" in expr


# ---------------------------------------------------------------------------
# Fake 基础设施
# ---------------------------------------------------------------------------


class FakeTextEmbedding:
    """固定向量文本向量：dim=4，每个文本一个确定性向量。"""

    def __init__(self, vectors: dict[str, list[float]]) -> None:
        self._vectors = vectors
        self.calls: list[list[str]] = []

    @property
    def dimension(self) -> int:
        return 4

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(texts)
        return [self._vectors.get(t, [0.0, 0.0, 0.0, 0.0]) for t in texts]


class FakeImageEmbedding:
    async def embed_image(self, image: ImageRef) -> list[float]:
        del image
        return [1.0, 0.0, 0.0, 0.0]


class FakeMilvusClient:
    """最小 MilvusClient 替身：按通道返回固定距离，记录 search 调用。"""

    def __init__(
        self,
        docs: list[dict[str, Any]],
        *,
        distance: dict[str, dict[str, float]] | None = None,
        fail: bool = False,
    ) -> None:
        self.docs = docs
        self.distance = distance or {}
        self.fail = fail
        self.calls: list[dict[str, Any]] = []

    def search(
        self,
        collection_name: str,
        data: Any,
        anns_field: str,
        search_params: dict[str, Any],
        limit: int,
        filter: str,
        output_fields: list[str],
    ) -> list[list[dict[str, Any]]]:
        del collection_name, data, search_params, output_fields
        if self.fail:
            raise RuntimeError("milvus connection refused (fake)")
        self.calls.append({"anns_field": anns_field, "filter": filter, "limit": limit})
        rows: list[dict[str, Any]] = []
        for doc in self.docs:
            offer_id = doc["offer_id"]
            d = self.distance.get(offer_id, {}).get(anns_field, 0.0)
            if d <= 0:
                continue
            rows.append({"id": offer_id, "distance": d, "entity": doc})
        return [rows[:limit]]


def make_settings(**overrides: Any) -> Settings:
    base: dict[str, Any] = {
        "ark_api_key": "k",
        "ark_base_url": "https://ark.example.local/v1",
        "ark_text_model": "t",
        "ark_vision_model": "v",
        "embedding_model": "embed-test",
        "milvus_uri": "https://milvus.example.local:19540",
        "milvus_token": "token",
        "milvus_collection": "offers",
    }
    base.update(overrides)
    return Settings(**base)


def entity(offer_id: str, **attrs: Any) -> dict[str, Any]:
    """Offer → Milvus entity（与索引工具同一字段形态：属性走 *_json 字段）。"""
    o = make_offer(offer_id, **attrs)
    payload: dict[str, Any] = o.model_dump(
        exclude={"identity_attributes", "variant_attributes", "descriptive_attributes"}
    )
    payload["identity_attributes_json"] = o.identity_attributes
    payload["variant_attributes_json"] = o.variant_attributes
    payload["descriptive_attributes_json"] = o.descriptive_attributes
    return payload


def make_image() -> ImageRef:
    return ImageRef(
        image_id="img-1",
        uri="data:image/jpeg;base64,AA==",
        content_type=ImageContentType.JPEG,
        sha256="c" * 64,
    )


class FakeMetrics:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}

    def inc(self, name: str, labels: dict[str, str] | None = None, value: float = 1.0) -> None:
        del labels
        self.counts[name] = self.counts.get(name, 0) + int(value)


async def local_adapter_from(tmp_path: Path, offers: list[Any]) -> LocalLexicalRetrievalAdapter:
    path = tmp_path / "snapshot.jsonl"
    path.write_text(
        "\n".join(o.model_dump_json() for o in offers) + "\n",
        encoding="utf-8",
    )
    return LocalLexicalRetrievalAdapter(path)


# ---------------------------------------------------------------------------
# 本地词法降级（§13.7）
# ---------------------------------------------------------------------------


async def test_local_retrieval_basic(tmp_path: Path) -> None:
    offers = [
        make_offer("o-sony", price=1899.0, title="Sony WH-1000XM5 头戴式降噪耳机"),
        make_offer(
            "o-apple",
            price=1599.0,
            brand="Apple",
            model="AirPods Pro",
            title="Apple AirPods Pro 蓝牙耳机",
        ),
        make_offer(
            "o-huawei", price=4999.0, brand="Huawei", model="Mate60", title="华为 Mate60 手机"
        ),
    ]
    adapter = await local_adapter_from(tmp_path, offers)
    query = RetrievalQuery(
        query_text="Sony 头戴式降噪耳机", hard_filters=HardFilters(category_id="headphone")
    )
    result = await adapter.search(query, top_k=10)
    assert isinstance(result, RetrievalResult)
    assert result.candidates[0].offer.offer_id == "o-sony"
    assert result.candidates[0].channel_sources == ["sparse"]
    assert result.candidates[0].dense_text_score is None  # 不伪造向量信号
    # o-huawei 经 identity 属性 "wearing_style 头戴式" 命中部分查询词（§13.3 字段同入）
    assert result.total_found == 3
    assert result.channel_counts == {"sparse": 3}
    assert result.fallback_used is False
    assert result.index_version is not None


async def test_local_retrieval_applies_hard_filters(tmp_path: Path) -> None:
    offers = [
        make_offer("o-cheap", price=899.0),
        make_offer("o-fit", price=1899.0),
        make_offer("o-expensive", price=2999.0),
    ]
    adapter = await local_adapter_from(tmp_path, offers)
    query = RetrievalQuery(
        query_text="索尼耳机",
        hard_filters=HardFilters(category_id="headphone", min_price=1000, max_price=2500),
    )
    result = await adapter.search(query, top_k=10)
    ids = {c.offer.offer_id for c in result.candidates}
    assert ids == {"o-fit"}


async def test_local_retrieval_zero_results(tmp_path: Path) -> None:
    adapter = await local_adapter_from(tmp_path, [make_offer("o1", price=100.0, brand="Sony")])
    result = await adapter.search(
        RetrievalQuery(query_text="不存在的东西", hard_filters=HardFilters(min_price=5000))
    )
    assert result.candidates == []
    assert result.total_found == 0


async def test_local_retrieval_snapshot_missing(tmp_path: Path) -> None:
    adapter = LocalLexicalRetrievalAdapter(tmp_path / "nope.jsonl")
    with pytest.raises(RetrievalUnavailableError):
        await adapter.search(RetrievalQuery(query_text="耳机"))


async def test_local_retrieval_bad_snapshot(tmp_path: Path) -> None:
    path = tmp_path / "bad.jsonl"
    path.write_text('{"offer_id": 1}\n', encoding="utf-8")
    adapter = LocalLexicalRetrievalAdapter(path)
    with pytest.raises(RetrievalUnavailableError):
        await adapter.search(RetrievalQuery(query_text="耳机"))


async def test_local_retrieval_uses_search_text_if_present(tmp_path: Path) -> None:
    """快照含 search_text 时直接使用（索引工具写入的产物）。"""
    o = make_offer("o1", price=1999.0).model_copy(
        update={"search_text": "耳机 Sony WH-1000XM5 头戴式降噪"}
    )
    adapter = await local_adapter_from(tmp_path, [o])
    result = await adapter.search(RetrievalQuery(query_text="降噪耳机"), top_k=10)
    assert result.candidates and result.candidates[0].offer.offer_id == "o1"


# ---------------------------------------------------------------------------
# Milvus 混合召回（§13.4）
# ---------------------------------------------------------------------------


def test_milvus_config_missing() -> None:
    with pytest.raises(ValueError, match="MILVUS"):
        MilvusHybridRetrievalAdapter(
            make_settings(milvus_uri=None, milvus_token=None, milvus_collection=None),
            text_embeddings=FakeTextEmbedding({}),
            local_fallback=LocalLexicalRetrievalAdapter(Path("x")),
        )


async def test_milvus_text_fusion_formula(tmp_path: Path) -> None:
    """§13.4 文本公式：recall = Σ(weight×signal) / Σ(available weights)。

    归一化后（min-max 于当前候选集）：
      dense  通道：o-dense=1.0, o-both=0.0
      sparse 通道：o-sparse=1.0, o-both=0.0
    查询词"索尼"（唯一 token）的 metadata 命中率：仅 o-sparse 命中（1.0）。
    """
    docs = [
        entity("o-dense", price=1899.0, title="Sony WH-1000XM5 降噪耳机"),
        entity("o-sparse", price=1799.0, title="索尼 头戴式 降噪 耳机"),
        entity("o-both", price=1699.0, title="Sony WH-1000XM5 头戴式降噪耳机"),
    ]
    client = FakeMilvusClient(
        docs,
        distance={
            "o-dense": {"text_dense": 0.9, "text_sparse": 0.0},
            "o-sparse": {"text_dense": 0.0, "text_sparse": 0.9},
            "o-both": {"text_dense": 0.8, "text_sparse": 0.6},
        },
    )
    adapter = MilvusHybridRetrievalAdapter(
        make_settings(),
        text_embeddings=FakeTextEmbedding({"索尼": [1.0, 0.0, 0.0, 0.0]}),
        local_fallback=LocalLexicalRetrievalAdapter(Path("x")),
        client=client,
    )
    result = await adapter.search(
        RetrievalQuery(query_text="索尼", hard_filters=HardFilters(category_id="headphone")),
        top_k=10,
    )
    assert {c.offer.offer_id for c in result.candidates} == {"o-dense", "o-sparse", "o-both"}
    by_id = {c.offer.offer_id: c for c in result.candidates}
    dense = by_id["o-dense"]
    assert dense.recall_score == pytest.approx(0.5 / 0.7)  # dense+metadata 归一化
    sparse = by_id["o-sparse"]
    assert sparse.recall_score == pytest.approx(1.0)  # sparse+metadata 全命中
    both = by_id["o-both"]
    assert both.recall_score == pytest.approx(0.0)
    assert both.channel_sources == ["dense", "sparse"]
    # filter 表达式传入 fake
    assert client.calls and client.calls[0]["filter"] == "category_id == 'headphone'"
    # 排序：o-sparse 最高
    assert result.candidates[0].offer.offer_id == "o-sparse"


async def test_milvus_image_channel_and_weights(tmp_path: Path) -> None:
    """有图片且图像向量可用：图像通道参与，公式切换为 §13.4 图片权重。"""
    docs = [entity("o1", price=1899.0)]
    client = FakeMilvusClient(docs, distance={"o1": {"text_dense": 0.9, "image_dense": 0.5}})
    adapter = MilvusHybridRetrievalAdapter(
        make_settings(),
        text_embeddings=FakeTextEmbedding({"索尼": [1.0, 0.0, 0.0, 0.0]}),
        image_embeddings=FakeImageEmbedding(),
        local_fallback=LocalLexicalRetrievalAdapter(Path("x")),
        client=client,
    )
    result = await adapter.search(
        RetrievalQuery(query_text="索尼"),
        image=make_image(),
        top_k=10,
    )
    c = result.candidates[0]
    # 单候选各通道归一化后=1.0；metadata 命中（默认标题含"索尼"）：
    # (0.35*1.0 + 0.25*1.0 + 0.2*1.0) / (0.35+0.25+0.2) = 1.0
    assert c.image_similarity is not None
    assert c.recall_score == pytest.approx(1.0)
    assert c.channel_sources == ["dense", "image"]
    assert result.channel_counts == {"dense": 1, "image": 1}
    fields_searched = {call["anns_field"] for call in client.calls}
    assert "text_dense" in fields_searched
    assert "image_dense" in fields_searched


async def test_milvus_skips_image_channel_when_unavailable(tmp_path: Path) -> None:
    """图像 provider 未配置：跳过图像通道，channel_counts 不出现 image。"""
    docs = [entity("o1", price=1899.0)]
    client = FakeMilvusClient(docs, distance={"o1": {"text_dense": 0.9}})
    adapter = MilvusHybridRetrievalAdapter(
        make_settings(),
        text_embeddings=FakeTextEmbedding({"索尼": [1.0, 0.0, 0.0, 0.0]}),
        image_embeddings=UnavailableImageEmbedding(),
        local_fallback=LocalLexicalRetrievalAdapter(Path("x")),
        client=client,
    )
    result = await adapter.search(RetrievalQuery(query_text="索尼"), image=make_image(), top_k=10)
    assert result.candidates[0].image_similarity is None
    assert "image" not in result.channel_counts
    assert result.channel_counts == {"dense": 1}
    fields_searched = {call["anns_field"] for call in client.calls}
    assert "image_dense" not in fields_searched


async def test_milvus_fallback_to_local_same_protocol(tmp_path: Path) -> None:
    """§13.7：Milvus 失败 → 本地词法降级，fallback_used=true，同一领域协议。"""
    offers = [
        make_offer("o1", price=1899.0, title="Sony WH-1000XM5 降噪耳机"),
        make_offer("o2", price=1799.0, title="索尼 头戴式降噪耳机"),
    ]
    local = await local_adapter_from(tmp_path, offers)
    failing = FakeMilvusClient([], fail=True)
    metrics = FakeMetrics()
    adapter = MilvusHybridRetrievalAdapter(
        make_settings(),
        text_embeddings=FakeTextEmbedding({"索尼耳机": [1.0, 0.0, 0.0, 0.0]}),
        local_fallback=local,
        client=failing,
        metrics=metrics,
    )
    result = await adapter.search(
        RetrievalQuery(query_text="索尼耳机", hard_filters=HardFilters(category_id="headphone")),
        top_k=10,
    )
    assert isinstance(result, RetrievalResult)
    assert result.fallback_used is True
    assert "milvus_unavailable" in (result.fallback_reason or "")
    # 查询词 索尼/耳机 均命中 → o2 词法分最高
    assert result.candidates[0].offer.offer_id == "o2"
    assert metrics.counts.get("provider_fallback_total") == 1


async def test_milvus_fallback_metrics_zero_result(tmp_path: Path) -> None:
    """本地降级零结果 → retrieval_zero_result_rate（由降级适配器上报）。"""
    failing = FakeMilvusClient([], fail=True)
    metrics = FakeMetrics()
    path = tmp_path / "snapshot.jsonl"
    path.write_text(
        make_offer("o1", price=99.0).model_dump_json() + "\n",
        encoding="utf-8",
    )
    local = LocalLexicalRetrievalAdapter(path, metrics=metrics)
    adapter = MilvusHybridRetrievalAdapter(
        make_settings(),
        text_embeddings=FakeTextEmbedding({"耳机": [1.0, 0.0, 0.0, 0.0]}),
        local_fallback=local,
        client=failing,
        metrics=metrics,
    )
    result = await adapter.search(
        RetrievalQuery(query_text="高价款", hard_filters=HardFilters(min_price=5000)),
        top_k=10,
    )
    assert result.candidates == []
    assert metrics.counts.get("provider_fallback_total") == 1
    assert metrics.counts.get("retrieval_zero_result_rate") == 1


async def test_milvus_entity_mapping_roundtrip() -> None:
    """Milvus entity（JSON 属性字段）→ Offer 映射（§13.2 / §21.2 字段映射）。"""
    o = make_offer("o1", price=1899.0, identity={"connectivity": "蓝牙", "wearing_style": "头戴式"})
    entity_doc = entity("o1", price=1899.0)
    # entity 中属性以 JSON 字符串形式出现（Milvus JSON 字段返回 str 或 dict 两种形态）
    entity_str = dict(entity_doc)
    entity_str["identity_attributes_json"] = json.dumps(o.identity_attributes, ensure_ascii=False)
    offer = _entity_to_offer(entity_str)
    assert offer.offer_id == "o1"
    assert offer.identity_attributes == {"connectivity": "蓝牙", "wearing_style": "头戴式"}
    assert offer.platform == "taobao"
    assert offer.price == 1899.0
    # dict 形态同样可用
    offer2 = _entity_to_offer(entity_doc)
    assert offer2.identity_attributes == offer.identity_attributes


async def test_milvus_retries_then_falls_back(tmp_path: Path) -> None:
    """单次失败在 max_network_attempts 内重试；全部失败才降级（§18）。"""
    offers = [make_offer("o1", price=1899.0, title="索尼 降噪耳机")]
    local = await local_adapter_from(tmp_path, offers)

    class FlakyClient(FakeMilvusClient):
        def __init__(self, docs: list[dict[str, Any]]) -> None:
            super().__init__(docs, distance={"o1": {"text_dense": 0.9}}, fail=False)
            self.failures_left = 1

        def search(self, *args: Any, **kwargs: Any) -> list[list[dict[str, Any]]]:
            if self.failures_left > 0:
                self.failures_left -= 1
                raise RuntimeError("transient failure")
            return super().search(*args, **kwargs)

    adapter = MilvusHybridRetrievalAdapter(
        make_settings(),
        text_embeddings=FakeTextEmbedding({"索尼耳机": [1.0, 0.0, 0.0, 0.0]}),
        local_fallback=local,
        client=FlakyClient([entity("o1", price=1899.0, title="索尼 降噪耳机")]),
    )
    result = await adapter.search(
        RetrievalQuery(query_text="索尼耳机"),
        top_k=10,
    )
    # 第一次 search 失败后重试成功 → 走 Milvus，不降级
    assert result.fallback_used is False
    assert result.candidates[0].offer.offer_id == "o1"
