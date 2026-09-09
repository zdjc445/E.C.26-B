"""检索候选池的确定性窗口选择（RAG 方案 §7.3）。"""

from __future__ import annotations

from dataclasses import dataclass

from shijiajing_agent.contracts import RetrievalCandidate


@dataclass(frozen=True)
class CandidateWindow:
    """召回池和评估窗口之间的选择结果。"""

    candidates: list[RetrievalCandidate]
    truncated_count: int


def select_candidate_window(
    candidates: list[RetrievalCandidate], limit: int = 60
) -> CandidateWindow:
    """按商品／卖家桶轮转，再按融合分回填评估窗口。

    ``source_product_id`` 只在同平台、同卖家／listing 下作为商品桶的一部分；
    因而不同卖家的报价不会因共享一个全局 SKU 键而被去重。缺少可靠身份时，
    每条 Offer 独立成桶，避免空值把大量候选错误聚成一组。
    """
    if limit < 1:
        raise ValueError("候选窗口上限必须大于 0")
    ordered = sorted(
        {item.offer.offer_id: item for item in candidates}.values(),
        key=lambda item: (-item.recall_score, item.offer.offer_id),
    )
    if len(ordered) <= limit:
        return CandidateWindow(candidates=ordered, truncated_count=0)

    buckets: dict[tuple[str, str, str], list[RetrievalCandidate]] = {}
    for candidate in ordered:
        offer = candidate.offer
        seller_or_listing = offer.shop_id or offer.source_offer_id or offer.offer_id
        product = offer.source_product_id or offer.offer_id
        key = (offer.platform, seller_or_listing, product)
        buckets.setdefault(key, []).append(candidate)

    # 桶的顺序由各桶最高融合分确定，桶内顺序已经按融合分和 offer_id 固定。
    bucket_values = sorted(
        buckets.values(),
        key=lambda items: (-items[0].recall_score, items[0].offer.offer_id),
    )
    selected: list[RetrievalCandidate] = []
    positions = [0] * len(bucket_values)
    while len(selected) < limit:
        progressed = False
        for bucket_index, bucket in enumerate(bucket_values):
            position = positions[bucket_index]
            if position >= len(bucket):
                continue
            selected.append(bucket[position])
            positions[bucket_index] += 1
            progressed = True
            if len(selected) >= limit:
                break
        if not progressed:
            break

    selected_ids = {item.offer.offer_id for item in selected}
    remaining = [item for item in ordered if item.offer.offer_id not in selected_ids]
    if len(selected) < limit:
        selected.extend(remaining[: limit - len(selected)])
    return CandidateWindow(
        candidates=selected,
        truncated_count=max(0, len(ordered) - len(selected)),
    )


__all__ = ["CandidateWindow", "select_candidate_window"]
