"""同款匹配、SPU 聚类与 SKU 拆分（方案 §14）。

处理顺序：
  Offer → 字段标准化 → 同款候选对生成 → 硬冲突否决 → 成对同款评分
  → SPU 聚类（complete-link）→ variant attributes 拆分 → 精确 SKU 比价组

全部为同步纯函数；标题/图像相似度通过注入的可调用对象提供
（领域层不直接依赖 Embedding 适配器）。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from dataclasses import field as dc_field
from typing import Protocol

from shijiajing_agent.contracts import NormalizedCandidate, Offer
from shijiajing_agent.domain.normalization import TaxonomyNormalizer
from shijiajing_agent.domain.open_world_normalization import open_text_equal


class TitleSimilarityFn(Protocol):
    def __call__(self, a: str, b: str) -> float: ...


class ImageSimilarityFn(Protocol):
    def __call__(self, offer_a: Offer, offer_b: Offer) -> float | None: ...

    # 权重（工厂与匹配器共用，保持单一来源）。


_SAME_ACCEPT = 0.88
_SAME_REVIEW = 0.74


def default_title_similarity(a: str, b: str) -> float:
    """生产默认标题相似度：token 相似度（无外部依赖，可离线复现）。"""
    return TaxonomyNormalizer.title_token_similarity(a, b)


def _candidate_title(candidate: NormalizedCandidate) -> str:
    """候选召回优先使用规范标题，扩大跨平台不同写法的召回。"""

    return candidate.offer.normalized_title or candidate.offer.title


def _pair_title_similarity(
    a: NormalizedCandidate,
    b: NormalizedCandidate,
    provider: Callable[[str, str], float],
) -> float:
    """最终评分保留原始标题差异；规范身份一致是强证据，但不直接给满分。"""

    raw_similarity = provider(a.offer.title, b.offer.title)
    canonical_a = a.offer.normalized_title
    canonical_b = b.offer.normalized_title
    if not canonical_a or not canonical_b:
        return raw_similarity
    canonical_similarity = min(0.95, provider(canonical_a, canonical_b))
    return max(raw_similarity, canonical_similarity)


def default_same_item_matcher(
    *,
    accept_threshold: float = _SAME_ACCEPT,
    review_threshold: float = _SAME_REVIEW,
) -> SameItemMatcher:
    """统一 SameItemMatcher 工厂（§10）：生产节点与评测共用同一工厂与参数。

    本阶段不改变评分公式；后续如生产接入图像相似度，只需扩展该工厂。
    """
    return SameItemMatcher(
        PairSimilarityProviders(title=default_title_similarity),
        accept_threshold=accept_threshold,
        review_threshold=review_threshold,
    )


@dataclass(frozen=True)
class PairSimilarityProviders:
    title: Callable[[str, str], float]
    image: Callable[[Offer, Offer], float | None] | None = None


@dataclass
class PairResult:
    a_id: str
    b_id: str
    score: float
    title_similarity: float | None = None
    identity_overlap: float | None = None
    image_similarity: float | None = None
    source_key_signal: float = 0.0
    hard_conflicts: list[str] = dc_field(default_factory=list[str])
    verdict: str = "different"

    # 权重。


_BASE_WEIGHTS = {
    "title": 0.35,
    "identity": 0.30,
    "image": 0.25,
    "source_key": 0.10,
}
_TITLE_PAIR_CANDIDATE_THRESHOLD = 0.85


class SameItemMatcher:
    def __init__(
        self,
        providers: PairSimilarityProviders,
        *,
        accept_threshold: float = _SAME_ACCEPT,
        review_threshold: float = _SAME_REVIEW,
    ) -> None:
        self._providers = providers
        self._accept = accept_threshold
        self._review = review_threshold

    # ------------------------------------------------------------------
    def generate_candidates(self, candidates: list[NormalizedCandidate]) -> list[tuple[int, int]]:
        """同款候选对生成（索引对）。"""
        pairs: list[tuple[int, int]] = []
        n = len(candidates)
        for i in range(n):
            for j in range(i + 1, n):
                if self._pair_eligible(candidates[i], candidates[j]):
                    pairs.append((i, j))
        return pairs

    def _pair_eligible(self, a: NormalizedCandidate, b: NormalizedCandidate) -> bool:
        # 只有双方动态概念都达到高置信时，品类冲突才作为硬隔离条件。
        if (
            a.normalized_category_concept
            and b.normalized_category_concept
            and a.normalized_category_concept != b.normalized_category_concept
            and a.dynamic_category_confidence >= 0.90
            and b.dynamic_category_confidence >= 0.90
        ):
            return False
        # 同款键完全一致
        if (
            a.offer.same_item_key
            and b.offer.same_item_key
            and a.offer.same_item_key == b.offer.same_item_key
        ):
            return True
        # 双方品牌均非空但不同 → 否决（提前剪枝）
        if a.normalized_brand and b.normalized_brand and a.normalized_brand != b.normalized_brand:
            return False
        # 双方型号均非空但不同 → 否决
        if a.normalized_model and b.normalized_model and a.normalized_model != b.normalized_model:
            return False
        # 没有可靠品牌+型号锚点时不生成自动聚类候选。
        if not (
            a.normalized_brand
            and b.normalized_brand
            and a.normalized_model
            and b.normalized_model
        ):
            return False
        if not open_text_equal(a.normalized_brand, b.normalized_brand):
            return False
        if not open_text_equal(a.normalized_model, b.normalized_model):
            return False
        return (
            self._providers.title(_candidate_title(a), _candidate_title(b))
            >= _TITLE_PAIR_CANDIDATE_THRESHOLD
        )

    # ------------------------------------------------------------------
    def judge_pair(self, a: NormalizedCandidate, b: NormalizedCandidate) -> PairResult:
        """成对判定：硬冲突否决 → 分数 → 结论。"""
        hard: list[str] = []
        if (
            a.normalized_category_concept
            and b.normalized_category_concept
            and a.normalized_category_concept != b.normalized_category_concept
            and a.dynamic_category_confidence >= 0.90
            and b.dynamic_category_confidence >= 0.90
        ):
            hard.append("category_concept")
        if a.normalized_brand and b.normalized_brand and a.normalized_brand != b.normalized_brand:
            hard.append("brand")
        if a.normalized_model and b.normalized_model and a.normalized_model != b.normalized_model:
            hard.append("model")
        # identity attributes 冲突。
        identity_keys = set(a.normalized_identity) | set(b.normalized_identity)
        for key in identity_keys:
            va, vb = a.normalized_identity.get(key), b.normalized_identity.get(key)
            if va and vb and va != vb:
                hard.append(f"identity:{key}")

        if hard:
            return PairResult(
                a_id=a.offer_id,
                b_id=b.offer_id,
                score=0.0,
                hard_conflicts=hard,
                verdict="different",
            )

        title_sim = _pair_title_similarity(a, b, self._providers.title)
        image_sim = self._providers.image(a.offer, b.offer) if self._providers.image else None

        # identity overlap：双方都有的属性中匹配的比例
        shared_keys = [
            k for k in identity_keys if k in a.normalized_identity and k in b.normalized_identity
        ]
        if shared_keys:
            identity_overlap = sum(
                1 for k in shared_keys if a.normalized_identity[k] == b.normalized_identity[k]
            ) / len(shared_keys)
        else:
            identity_overlap = None

        same_key = (
            a.offer.same_item_key
            and b.offer.same_item_key
            and a.offer.same_item_key == b.offer.same_item_key
        )
        source_signal = 1.0 if same_key else 0.0

        # 缺失维度不参与，其余权重重新归一化。
        dims = {"title": title_sim}
        if identity_overlap is not None:
            dims["identity"] = identity_overlap
        if image_sim is not None:
            dims["image"] = image_sim
        if same_key:
            dims["source_key"] = source_signal

        weights = {k: _BASE_WEIGHTS[k] for k in dims}
        total_w = sum(weights.values())
        score = sum(weights[k] * dims[k] for k in dims) / total_w if total_w else 0.0

        if score >= self._accept:
            verdict = "same"
        elif score >= self._review:
            verdict = "review"
        else:
            verdict = "different"

        if (
            not same_key
            and not (
                a.normalized_brand
                and b.normalized_brand
                and a.normalized_model
                and b.normalized_model
            )
            and verdict == "same"
        ):
            verdict = "review"

        return PairResult(
            a_id=a.offer_id,
            b_id=b.offer_id,
            score=score,
            title_similarity=title_sim,
            identity_overlap=identity_overlap,
            image_similarity=image_sim,
            source_key_signal=source_signal,
            hard_conflicts=hard,
            verdict=verdict,
        )

    # ------------------------------------------------------------------
    def cluster(
        self, candidates: list[NormalizedCandidate], pairs: list[tuple[int, int]]
    ) -> list[list[int]]:
        """complete-link 层次聚类。

        合并两个簇时，跨簇每一对 Offer 都必须满足同款阈值或具有相同的权威 same_item_key，
        避免 A≈B、B≈C 导致 A 与 C 被错误传递合并。
        """
        n = len(candidates)
        scores: dict[tuple[int, int], PairResult] = {}
        for i, j in pairs:
            scores[(i, j)] = self.judge_pair(candidates[i], candidates[j])

        # 预计算 pair → 是否可合并（含权威 same_item_key 旁路）
        mergeable: dict[tuple[int, int], bool] = {}
        for (i, j), r in scores.items():
            a, b = candidates[i], candidates[j]
            auth = (
                bool(a.offer.same_item_key)
                and bool(b.offer.same_item_key)
                and a.offer.same_item_key == b.offer.same_item_key
            )
            mergeable[(i, j)] = r.verdict == "same" or auth
            mergeable[(j, i)] = mergeable[(i, j)]

        clusters: list[set[int]] = [{i} for i in range(n)]
        changed = True
        while changed:
            changed = False
            for ci in range(len(clusters)):
                for cj in range(ci + 1, len(clusters)):
                    if self._complete_link_ok(clusters[ci], clusters[cj], mergeable):
                        clusters[ci] |= clusters[cj]
                        del clusters[cj]
                        changed = True
                        break
                if changed:
                    break
        return [sorted(c) for c in clusters]

    @staticmethod
    def _complete_link_ok(
        ca: set[int], cb: set[int], mergeable: dict[tuple[int, int], bool]
    ) -> bool:
        for i in ca:
            for j in cb:
                if not mergeable.get((i, j), False):
                    return False
        return True
