"""排序节点（方案 §15）。

LLM 不参与数值排序。显式排序优先于推荐分；最终稳定 tie-breaker 为
``group_id`` 升序。只修改 ``sort_by`` / 软偏好时复用既有结果（§10.1）。
"""

from __future__ import annotations

from typing import Any

from shijiajing_agent.contracts import ShoppingConstraints, SortBy
from shijiajing_agent.domain.ranking import GroupRanker
from shijiajing_agent.nodes.node_support import timed
from shijiajing_agent.ports.dependencies import AgentDependenciesPort
from shijiajing_agent.state import AgentState


def make_rank_groups_node(deps: AgentDependenciesPort) -> Any:
    """多阶段排序（§15.2–15.4）。"""

    @timed("rank_groups")
    async def rank_groups_node(state: AgentState) -> dict[str, Any]:
        if not (state.get("dirty_flags") or {}).get("ranking_dirty", True):
            if state.get("ranked_groups"):
                return {"next_action": "ranked"}
        groups = state.get("sku_groups") or []
        if not groups:
            return {"ranked_groups": [], "next_action": "ranked"}
        constraints = state.get("effective_constraints") or ShoppingConstraints()
        sort_by = (
            SortBy(constraints.sort_by.value) if constraints.sort_by.value else SortBy.RECOMMENDED
        )
        preferences = list(constraints.preferences.value) if constraints.preferences.value else []
        ranker = GroupRanker(preference_weights=deps.settings.preference_weights)
        result = ranker.rank(groups, constraints, sort_by=sort_by, preferences=preferences)
        return {"ranked_groups": result.ranked, "next_action": "ranked"}

    return rank_groups_node
