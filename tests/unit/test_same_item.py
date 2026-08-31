"""同款匹配：候选对、硬冲突、complete-link 聚类（§14.2–14.5）。"""

from __future__ import annotations

import pytest

from shijiajing_agent.contracts import NormalizedCandidate, Offer
from shijiajing_agent.domain.normalization import TaxonomyNormalizer
from shijiajing_agent.domain.same_item import PairSimilarityProviders, SameItemMatcher
from tests.unit.conftest import offer


def normalize(
    taxonomy,
    o: Offer,
    *,
    category_concept: str | None = None,
    category_confidence: float = 0.0,
) -> NormalizedCandidate:
    candidate = TaxonomyNormalizer(taxonomy).normalize_offer(o)
    return candidate.model_copy(
        update={
            "normalized_category_concept": category_concept,
            "dynamic_category_confidence": category_confidence,
        }
    )


def use_raw_title(candidate: NormalizedCandidate) -> NormalizedCandidate:
    return candidate.model_copy(
        update={"offer": candidate.offer.model_copy(update={"normalized_title": None})}
    )


@pytest.fixture
def matcher(taxonomy):
    return SameItemMatcher(
        PairSimilarityProviders(title=lambda a, b: 0.95, image=None),
    )


class TestPairEligibility:
    def test_same_item_key_matches(self, matcher, taxonomy):
        a = normalize(taxonomy, offer("a1", same_item_key="k1"))
        b = normalize(taxonomy, offer("b1", same_item_key="k1"))
        pairs = matcher.generate_candidates([a, b])
        assert pairs == [(0, 1)]

    def test_high_confidence_dynamic_category_conflict_rejected(self, matcher, taxonomy):
        a = normalize(taxonomy, offer("a1"), category_concept="headphone", category_confidence=0.95)
        b = normalize(taxonomy, offer("b1"), category_concept="sneaker", category_confidence=0.95)
        assert matcher.generate_candidates([a, b]) == []

    def test_different_brand_rejected(self, matcher, taxonomy):
        a = normalize(taxonomy, offer("a1", brand="Sony"))
        b = normalize(taxonomy, offer("b1", brand="Bose"))
        assert matcher.generate_candidates([a, b]) == []

    def test_title_similarity_gates_pair(self, taxonomy):
        m = SameItemMatcher(
            PairSimilarityProviders(title=lambda a, b: 0.5),
        )
        a = normalize(taxonomy, offer("a1", brand="Sony"))
        b = normalize(taxonomy, offer("b1", brand="Sony", model=None))
        assert m.generate_candidates([a, b]) == []


class TestHardConflicts:
    """§14.3 硬冲突否决。"""

    def test_identity_attribute_conflict(self, matcher, taxonomy):
        a = normalize(taxonomy, offer("a1", identity={"connectivity": "蓝牙"}))
        b = normalize(taxonomy, offer("b1", identity={"connectivity": "有线"}))
        r = matcher.judge_pair(a, b)
        assert r.verdict == "different"
        assert r.score == 0.0
        assert "identity:connectivity" in r.hard_conflicts

    def test_brand_conflict_zero_score(self, matcher, taxonomy):
        a = normalize(taxonomy, offer("a1", brand="Sony"))
        b = normalize(taxonomy, offer("b1", brand="Bose"))
        r = matcher.judge_pair(a, b)
        assert r.score == 0.0
        assert r.verdict == "different"

    def test_model_conflict_zero_score(self, matcher, taxonomy):
        a = normalize(taxonomy, offer("a1", model="WH-1000XM5"))
        b = normalize(taxonomy, offer("b1", model="WH-1000XM4"))
        r = matcher.judge_pair(a, b)
        assert r.verdict == "different"


class TestScoring:
    def test_authoritative_key_signal(self, matcher, taxonomy):
        a = normalize(taxonomy, offer("a1", same_item_key="k1", title="完全不同的标题"))
        b = normalize(taxonomy, offer("b1", same_item_key="k1", title="另一完全不同标题"))
        # 权威 same_item_key 一致 → source_key_signal=1；即使标题不同，也不否决（§14.4 旁路）
        pairs = matcher.generate_candidates([a, b])
        assert pairs == [(0, 1)]
        r = matcher.judge_pair(a, b)
        assert r.source_key_signal == 1.0

    def test_missing_dimensions_renormalized(self, taxonomy):
        """缺失维度不参与，其余权重重新归一化（§14.4）。"""
        m = SameItemMatcher(
            PairSimilarityProviders(title=lambda a, b: 1.0, image=None),
        )
        a = normalize(taxonomy, offer("a1"))
        b = normalize(taxonomy, offer("b1"))
        r = m.judge_pair(a, b)
        # 只有 title 维度 → score = 1.0 * (0.35/0.35) = 1.0
        assert r.score == pytest.approx(1.0)


class TestCompleteLinkClustering:
    """§14.5 防止 A≈B、B≈C 传递误合并。"""

    def test_no_transitive_merge(self, taxonomy):
        # 构造 title 相似度矩阵：AB 高、BC 高、AC 低
        sims = {
            ("a", "b"): 0.99,
            ("b", "c"): 0.99,
            ("a", "c"): 0.1,
        }
        m = SameItemMatcher(
            PairSimilarityProviders(title=lambda x, y: sims.get((x, y), sims.get((y, x), 0.0))),
        )
        offers = [
            use_raw_title(normalize(taxonomy, offer("a", title="a"))),
            use_raw_title(normalize(taxonomy, offer("b", title="b"))),
            use_raw_title(normalize(taxonomy, offer("c", title="c"))),
        ]
        pairs = m.generate_candidates(offers)
        clusters = m.cluster(offers, pairs)
        # A≈B 且 B≈C，但 A≉C → complete-link 禁止三者合并
        assert clusters == [[0, 1], [2]]

    def test_all_pairs_merge(self, taxonomy):
        m = SameItemMatcher(
            PairSimilarityProviders(title=lambda a, b: 0.99),
        )
        offers = [
            normalize(taxonomy, offer("a")),
            normalize(taxonomy, offer("b")),
            normalize(taxonomy, offer("c")),
        ]
        clusters = m.cluster(offers, m.generate_candidates(offers))
        assert clusters == [[0, 1, 2]]

    def test_same_item_key_bridges_clusters(self, taxonomy):
        """权威 same_item_key 允许跨标题差异合并。"""
        m = SameItemMatcher(
            PairSimilarityProviders(title=lambda a, b: 0.99),
        )
        offers = [
            normalize(taxonomy, offer("a", same_item_key="k1", model=None)),
            normalize(taxonomy, offer("b", same_item_key="k1", model=None)),
            normalize(taxonomy, offer("c", same_item_key="k1", model=None)),
        ]
        clusters = m.cluster(offers, m.generate_candidates(offers))
        assert clusters == [[0, 1, 2]]
