"""RetrievalSubgraph：查询改写、召回、放宽和候选标准化。"""

from __future__ import annotations

from typing import Any, cast

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from shijiajing_agent.nodes.retrieval_nodes import (
    make_normalize_candidates_node,
    make_relax_recognition_constraints_node,
    make_retrieve_candidates_node,
    make_rewrite_query_node,
)
from shijiajing_agent.ports.dependencies import AgentDependenciesPort
from shijiajing_agent.routing import route_after_relax, route_retrieval
from shijiajing_agent.state import AgentState


def build_retrieval_subgraph(
    deps: AgentDependenciesPort,
) -> CompiledStateGraph[AgentState, None, AgentState, AgentState]:
    graph: Any = StateGraph(AgentState)
    graph.add_node("rewrite_query", make_rewrite_query_node(deps))
    graph.add_node("retrieve_candidates", make_retrieve_candidates_node(deps))
    graph.add_node("relax_recognition_constraints", make_relax_recognition_constraints_node(deps))
    graph.add_node("normalize_candidates", make_normalize_candidates_node(deps))
    graph.add_edge(START, "rewrite_query")
    graph.add_edge("rewrite_query", "retrieve_candidates")
    graph.add_conditional_edges(
        "retrieve_candidates",
        route_retrieval,
        {
            "normalize_candidates": "normalize_candidates",
            "relax_recognition_constraints": "relax_recognition_constraints",
            "build_no_results": END,
            "build_failed_response": END,
        },
    )
    graph.add_conditional_edges(
        "relax_recognition_constraints",
        route_after_relax,
        {"rewrite_query": "rewrite_query", "build_no_results": END},
    )
    graph.add_edge("normalize_candidates", END)
    return cast(
        CompiledStateGraph[AgentState, None, AgentState, AgentState],
        graph.compile(name="retrieval-subgraph"),
    )
