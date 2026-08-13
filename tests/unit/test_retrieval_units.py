"""检索领域单元：search_text 构造（§13.3）、硬过滤谓词（§13.5）、词法核心。"""

from __future__ import annotations

from shijiajing_agent.adapters.lexical import Bm25Index, query_sparse_vector, token_id, tokenize
from shijiajing_agent.contracts import HardFilters, Offer
from shijiajing_agent.domain.filters import offer_matches_hard_filters
from shijiajing_agent.domain.normalization import build_search_text
from shijiajing_agent.domain.taxonomy import Taxonomy
from tests.unit.conftest import offer

# ---------------------------------------------------------------------------
# §13.3 search_text 组成
# ---------------------------------------------------------------------------


def test_build_search_text_order(mini_taxonomy: Taxonomy) -> None:
    o = offer("o1", price=1999.0, title="索尼头戴式降噪耳机")
    text = build_search_text(o, category_name="耳机", taxonomy=mini_taxonomy)
    assert text.startswith("耳机 Sony WH-1000XM5 索尼头戴式降噪耳机")
    # identity 属性键值同入（§13.3 "字段名和值同时进入文本"）
    assert "connectivity 蓝牙" in text
    assert "color 黑色" in text


def test_build_search_text_includes_descriptive_tags(mini_taxonomy: Taxonomy) -> None:
    o = offer("o1", price=1999.0).model_copy(
        update={"descriptive_attributes": {"noise_cancellation": "主动降噪"}}
    )
    text = build_search_text(o, category_name="耳机", taxonomy=mini_taxonomy)
    assert "noise_cancellation 主动降噪" in text


def test_build_search_text_empty_ok(mini_taxonomy: Taxonomy) -> None:
    o = Offer(offer_id="o1", platform="taobao")
    text = build_search_text(o, category_name=None, taxonomy=mini_taxonomy)
    assert text == ""


# ---------------------------------------------------------------------------
# §13.5 硬过滤谓词（与 Milvus filter 表达式同语义）
# ---------------------------------------------------------------------------


def test_hard_filters_all_fields() -> None:
    o = offer("o1", price=1200.0, rating=4.6)
    hf = HardFilters(
        category_id="headphone",
        min_price=1000,
        max_price=1500,
        platforms=["taobao"],
        min_rating=4.5,
        brand="Sony",
        model="WH-1000XM5",
    )
    assert offer_matches_hard_filters(o, hf)
    assert offer_matches_hard_filters(o, HardFilters())  # 空过滤全部通过


def test_hard_filter_price_and_rating_reject() -> None:
    o = offer("o1", price=800.0, rating=4.2)
    assert not offer_matches_hard_filters(o, HardFilters(min_price=1000))
    assert not offer_matches_hard_filters(o, HardFilters(min_rating=4.5))
    assert offer_matches_hard_filters(o, HardFilters())


def test_hard_filter_platform_brand_model() -> None:
    o = offer("o1", price=1200.0, platform="jd")
    assert not offer_matches_hard_filters(o, HardFilters(platforms=["taobao"]))
    assert not offer_matches_hard_filters(o, HardFilters(brand="Apple"))
    assert not offer_matches_hard_filters(o, HardFilters(model="WH-1000XM4"))


def test_hard_filter_price_null_offer() -> None:
    o = Offer(offer_id="o1", platform="taobao", category_id="headphone")  # price=None
    assert not offer_matches_hard_filters(o, HardFilters(max_price=1000))
    assert offer_matches_hard_filters(o, HardFilters(category_id="headphone"))


# ---------------------------------------------------------------------------
# 词法核心（tokenizer / BM25 / sparse 向量）
# ---------------------------------------------------------------------------


def test_tokenize_mixed_latin_cjk() -> None:
    tokens = tokenize("Sony WH-1000XM5 头戴式降噪耳机")
    assert "sony" in tokens
    assert "wh-1000xm5" in tokens
    assert "头戴" in tokens and "戴式" in tokens
    assert "降噪" in tokens and "耳机" in tokens


def test_query_sparse_vector_counts() -> None:
    v = query_sparse_vector("索尼 索尼 耳机")
    # key 为稳定 64 位 int（Milvus SPARSE_FLOAT_VECTOR），索引/查询共用 token_id
    assert v.get(token_id("索尼")) == 2 and v.get(token_id("耳机")) == 1
    assert sum(v.values()) == 3  # 总和 = 输入 token 数


def test_bm25_ranks_relevant_doc_first() -> None:
    index = Bm25Index(
        [
            "Sony WH-1000XM5 头戴式降噪耳机",
            "Apple AirPods Pro 真无线蓝牙耳机",
            "华为 Mate60 Pro 智能手机",
        ]
    )
    ranked = index.score(tokenize("Sony 头戴式耳机"))
    assert ranked, "必须命中至少一个文档"
    top_doc, top_score = ranked[0]
    assert top_doc == 0
    assert top_score > 0


def test_bm25_empty_corpus() -> None:
    index = Bm25Index([])
    assert index.score(tokenize("耳机")) == []


def test_bm25_low_frequency_term_boosts() -> None:
    """低频词 idf 更高：查“降噪耳机”应优先命中含“降噪”的文档。"""
    index = Bm25Index(["头戴式降噪耳机", "普通耳机", "普通耳机"])
    ranked = index.score(tokenize("降噪耳机"))
    assert ranked and ranked[0][0] == 0
