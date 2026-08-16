"""同款候选、硬冲突评分与 complete-link 聚类。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from product_matching.models import NormalizedCandidate, Offer, PairResult
from product_matching.taxonomy import Taxonomy

_BASE_WEIGHTS = {
    "title": 0.35,
    "identity": 0.30,
    "image": 0.25,
    "source_key": 0.10,
}
_TITLE_PAIR_CANDIDATE_THRESHOLD = 0.85


@dataclass(frozen=True)
class PairSimilarityProviders:
    title: Callable[[str, str], float]
    image: Callable[[Offer, Offer], float | None] | None = None


class SameItemMatcher:
    def __init__(
        self,
        taxonomy: Taxonomy,
        providers: PairSimilarityProviders,
        *,
        accept_threshold: float = 0.82,
        review_threshold: float = 0.68,
    ) -> None:
        self._taxonomy = taxonomy
        self._providers = providers
        self._accept = accept_threshold
        self._review = review_threshold

    def generate_candidates(self, candidates: list[NormalizedCandidate]) -> list[tuple[int, int]]:
        pairs: list[tuple[int, int]] = []
        for left_index in range(len(candidates)):
            for right_index in range(left_index + 1, len(candidates)):
                if self._pair_eligible(candidates[left_index], candidates[right_index]):
                    pairs.append((left_index, right_index))
        return pairs

    def _pair_eligible(self, a: NormalizedCandidate, b: NormalizedCandidate) -> bool:
        if (
            a.normalized_category_id
            and b.normalized_category_id
            and a.normalized_category_id != b.normalized_category_id
        ):
            return False
        if (
            a.offer.same_item_key
            and b.offer.same_item_key
            and a.offer.same_item_key == b.offer.same_item_key
        ):
            return True
        if a.normalized_brand and b.normalized_brand and a.normalized_brand != b.normalized_brand:
            return False
        if a.normalized_model and b.normalized_model and a.normalized_model != b.normalized_model:
            return False
        if a.normalized_category_id and a.normalized_category_id == b.normalized_category_id:
            if a.normalized_brand or b.normalized_brand:
                if not a.normalized_brand or not b.normalized_brand:
                    return False
                return (
                    self._providers.title(a.offer.title, b.offer.title)
                    >= _TITLE_PAIR_CANDIDATE_THRESHOLD
                )
        return False

    def judge_pair(self, a: NormalizedCandidate, b: NormalizedCandidate) -> PairResult:
        hard_conflicts: list[str] = []
        if (
            a.normalized_category_id
            and b.normalized_category_id
            and a.normalized_category_id != b.normalized_category_id
        ):
            hard_conflicts.append("category")
        if a.normalized_brand and b.normalized_brand and a.normalized_brand != b.normalized_brand:
            hard_conflicts.append("brand")
        if a.normalized_model and b.normalized_model and a.normalized_model != b.normalized_model:
            hard_conflicts.append("model")

        identity_keys = set(a.normalized_identity) | set(b.normalized_identity)
        for key in identity_keys:
            left = a.normalized_identity.get(key)
            right = b.normalized_identity.get(key)
            if left and right and left != right:
                hard_conflicts.append(f"identity:{key}")

        if hard_conflicts:
            return PairResult(
                a_id=a.offer_id,
                b_id=b.offer_id,
                score=0.0,
                hard_conflicts=hard_conflicts,
                verdict="different",
            )

        title_similarity = self._providers.title(a.offer.title, b.offer.title)
        image_similarity = (
            self._providers.image(a.offer, b.offer) if self._providers.image else None
        )
        shared_identity_keys = [
            key
            for key in identity_keys
            if key in a.normalized_identity and key in b.normalized_identity
        ]
        identity_overlap = (
            sum(
                1
                for key in shared_identity_keys
                if a.normalized_identity[key] == b.normalized_identity[key]
            )
            / len(shared_identity_keys)
            if shared_identity_keys
            else None
        )
        same_source_key = bool(
            a.offer.same_item_key
            and b.offer.same_item_key
            and a.offer.same_item_key == b.offer.same_item_key
        )

        dimensions = {"title": title_similarity}
        if identity_overlap is not None:
            dimensions["identity"] = identity_overlap
        if image_similarity is not None:
            dimensions["image"] = image_similarity
        if same_source_key:
            dimensions["source_key"] = 1.0

        weights = {key: _BASE_WEIGHTS[key] for key in dimensions}
        total_weight = sum(weights.values())
        score = (
            sum(weights[key] * dimensions[key] for key in dimensions) / total_weight
            if total_weight
            else 0.0
        )
        if score >= self._accept:
            verdict = "same"
        elif score >= self._review:
            verdict = "review"
        else:
            verdict = "different"
        return PairResult(
            a_id=a.offer_id,
            b_id=b.offer_id,
            score=score,
            title_similarity=title_similarity,
            identity_overlap=identity_overlap,
            image_similarity=image_similarity,
            source_key_signal=1.0 if same_source_key else 0.0,
            hard_conflicts=hard_conflicts,
            verdict=verdict,
        )

    def cluster(
        self, candidates: list[NormalizedCandidate], pairs: list[tuple[int, int]]
    ) -> list[list[int]]:
        pair_results = {
            (left, right): self.judge_pair(candidates[left], candidates[right])
            for left, right in pairs
        }
        mergeable: dict[tuple[int, int], bool] = {}
        for (left, right), result in pair_results.items():
            a, b = candidates[left], candidates[right]
            authoritative = bool(
                a.offer.same_item_key
                and b.offer.same_item_key
                and a.offer.same_item_key == b.offer.same_item_key
            )
            mergeable[(left, right)] = result.verdict == "same" or authoritative
            mergeable[(right, left)] = mergeable[(left, right)]

        clusters: list[set[int]] = [{index} for index in range(len(candidates))]
        changed = True
        while changed:
            changed = False
            for left_cluster in range(len(clusters)):
                for right_cluster in range(left_cluster + 1, len(clusters)):
                    if self._complete_link_ok(
                        clusters[left_cluster], clusters[right_cluster], mergeable
                    ):
                        clusters[left_cluster] |= clusters[right_cluster]
                        del clusters[right_cluster]
                        changed = True
                        break
                if changed:
                    break
        return [sorted(cluster) for cluster in clusters]

    @staticmethod
    def _complete_link_ok(
        left_cluster: set[int],
        right_cluster: set[int],
        mergeable: dict[tuple[int, int], bool],
    ) -> bool:
        return all(
            mergeable.get((left, right), False) for left in left_cluster for right in right_cluster
        )
