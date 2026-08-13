"""主图装配（方案 §9.1）。节点全部由依赖注入创建，端口由 adapters/ 提供。"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from shijiajing_agent.nodes.input_nodes import (
    load_session_node,
    prepare_subject_node,
    validate_input_node,
)
from shijiajing_agent.nodes.intent_nodes import (
    make_merge_constraints_node,
    make_parse_intent_node,
    make_validate_constraints_node,
)
from shijiajing_agent.nodes.matching_nodes import make_match_same_item_node, make_split_sku_node
from shijiajing_agent.nodes.ranking_nodes import make_rank_groups_node
from shijiajing_agent.nodes.recognition_nodes import (
    make_apply_correction_node,
    make_normalize_recognition_node,
    make_recognize_image_node,
)
from shijiajing_agent.nodes.response_nodes import (
    make_build_clarification_node,
    make_build_evidence_node,
    make_build_failed_node,
    make_build_no_results_node,
    make_build_response_node,
    make_generate_explanation_node,
)
from shijiajing_agent.nodes.retrieval_nodes import (
    make_normalize_candidates_node,
    make_relax_recognition_constraints_node,
    make_retrieve_candidates_node,
    make_rewrite_query_node,
)
from shijiajing_agent.routing import (
    route_after_relax,
    route_after_validation,
    route_recognition,
    route_retrieval,
)
from shijiajing_agent.state import AgentState


def build_graph(deps: Any) -> Any:
    """按 §9.1 主图装配。deps 需包含 taxonomy、settings 与全部端口。"""
    g: Any = StateGraph(AgentState)

    g.add_node("validate_input", validate_input_node)
    g.add_node("load_session", load_session_node)
    g.add_node("prepare_subject", prepare_subject_node)
    g.add_node("recognize_image", make_recognize_image_node(deps))
    g.add_node("apply_correction", make_apply_correction_node(deps))
    g.add_node("normalize_recognition", make_normalize_recognition_node(deps))
    g.add_node("parse_intent", make_parse_intent_node(deps))
    g.add_node("merge_constraints", make_merge_constraints_node(deps))
    g.add_node("validate_constraints", make_validate_constraints_node(deps))
    g.add_node("build_clarification", make_build_clarification_node(deps))
    g.add_node("rewrite_query", make_rewrite_query_node(deps))
    g.add_node("retrieve_candidates", make_retrieve_candidates_node(deps))
    g.add_node("relax_recognition_constraints", make_relax_recognition_constraints_node(deps))
    g.add_node("normalize_candidates", make_normalize_candidates_node(deps))
    g.add_node("match_same_item", make_match_same_item_node(deps))
    g.add_node("split_sku", make_split_sku_node(deps))
    g.add_node("rank_groups", make_rank_groups_node(deps))
    g.add_node("build_evidence", make_build_evidence_node(deps))
    g.add_node("generate_explanation", make_generate_explanation_node(deps))
    g.add_node("build_response", make_build_response_node(deps))
    g.add_node("build_no_results", make_build_no_results_node(deps))
    g.add_node("build_failed_response", make_build_failed_node(deps))

    g.add_edge(START, "validate_input")
    g.add_edge("validate_input", "load_session")
    g.add_edge("load_session", "prepare_subject")

    g.add_conditional_edges(
        "prepare_subject",
        route_recognition,
        {"recognize_image": "recognize_image", "apply_correction": "apply_correction"},
    )
    g.add_edge("recognize_image", "normalize_recognition")
    g.add_edge("apply_correction", "normalize_recognition")
    g.add_edge("normalize_recognition", "parse_intent")
    g.add_edge("parse_intent", "merge_constraints")
    g.add_edge("merge_constraints", "validate_constraints")

    g.add_conditional_edges(
        "validate_constraints",
        route_after_validation,
        {"build_clarification": "build_clarification", "rewrite_query": "rewrite_query"},
    )
    g.add_edge("build_clarification", "build_response")
    g.add_edge("rewrite_query", "retrieve_candidates")

    g.add_conditional_edges(
        "retrieve_candidates",
        route_retrieval,
        {
            "normalize_candidates": "normalize_candidates",
            "relax_recognition_constraints": "relax_recognition_constraints",
            "build_no_results": "build_no_results",
            "build_failed_response": "build_failed_response",
        },
    )
    g.add_conditional_edges(
        "relax_recognition_constraints",
        route_after_relax,
        {"rewrite_query": "rewrite_query", "build_no_results": "build_no_results"},
    )

    g.add_edge("normalize_candidates", "match_same_item")
    g.add_edge("match_same_item", "split_sku")
    g.add_edge("split_sku", "rank_groups")
    g.add_edge("rank_groups", "build_evidence")
    g.add_edge("build_evidence", "generate_explanation")
    g.add_edge("generate_explanation", "build_response")

    g.add_edge("build_no_results", "build_response")

    # build_failed_response 已产出完整 FAILED 响应，直接结束
    g.add_edge("build_failed_response", END)

    g.add_edge("build_response", END)
    return g.compile()
