"""同款匹配与 SKU 拆分节点（方案 §14）。

- ``match_same_item``：候选 → SPU clusters。算法失败时不合并，返回独立商品（§9.2）。
- ``split_sku``：SPU → SKU groups；缺少关键销售属性时不跨平台比价（§14.6）。
"""

from __future__ import annotations

from typing import Any

from shijiajing_agent.domain.normalization import TaxonomyNormalizer
from shijiajing_agent.domain.same_item import PairSimilarityProviders, SameItemMatcher
from shijiajing_agent.domain.sku import SkuSplitter, spu_id_for
from shijiajing_agent.nodes.node_support import timed
from shijiajing_agent.state import AgentState


def make_match_same_item_node(deps: Any) -> Any:
    """同款匹配（§14.2–14.5）。异常时每个候选独立成 SPU，不误比价。"""

    @timed("match_same_item")
    async def match_same_item_node(state: AgentState) -> dict[str, Any]:
        if not (state.get("dirty_flags") or {}).get("matching_dirty", True):
            if state.get("spu_clusters"):
                return {"next_action": "spu_ready"}
        normalized = state.get("normalized_candidates") or []
        if not normalized:
            return {"spu_clusters": [], "next_action": "spu_ready"}
        try:
            matcher = SameItemMatcher(
                deps.taxonomy,
                PairSimilarityProviders(title=TaxonomyNormalizer.title_token_similarity),
            )
            pairs = matcher.generate_candidates(normalized)
            clusters = matcher.cluster(normalized, pairs)
            return {"spu_clusters": clusters, "next_action": "spu_ready"}
        except Exception as exc:
            # §9.2：匹配异常时不合并，候选独立展示
            independent = [[i] for i in range(len(normalized))]
            return {
                "spu_clusters": independent,
                "next_action": "spu_ready",
                "notices": [*list(state.get("notices") or []), "同款匹配异常，候选按独立商品展示"],
                "errors": [
                    *list(state.get("errors") or []),
                    {
                        "node_name": "match_same_item",
                        "error_code": "INTERNAL_ERROR",
                        "message": str(exc),
                    },
                ],
            }

    return match_same_item_node


def make_split_sku_node(deps: Any) -> Any:
    """SKU 拆分（§14.6–14.7）。"""

    @timed("split_sku")
    async def split_sku_node(state: AgentState) -> dict[str, Any]:
        normalized = state.get("normalized_candidates") or []
        clusters = state.get("spu_clusters") or []
        splitter = SkuSplitter(deps.taxonomy)
        groups: list[Any] = []
        for cluster in clusters:
            members = [normalized[i] for i in cluster]
            if not members:
                continue
            groups.extend(splitter.split_spu(members, spu_id_for(members)))
        return {"sku_groups": groups, "next_action": "sku_ready"}

    return split_sku_node
