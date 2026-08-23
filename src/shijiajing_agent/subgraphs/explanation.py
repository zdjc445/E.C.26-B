"""ExplanationSubgraph：证据构建和事实一致性解释。"""

from __future__ import annotations

from typing import Any, cast

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from shijiajing_agent.nodes.response_nodes import (
    make_build_evidence_node,
    make_generate_explanation_node,
)
from shijiajing_agent.ports.dependencies import AgentDependenciesPort
from shijiajing_agent.state import AgentState


def build_explanation_subgraph(
    deps: AgentDependenciesPort,
) -> CompiledStateGraph[AgentState, None, AgentState, AgentState]:
    graph: Any = StateGraph(AgentState)
    graph.add_node("build_evidence", make_build_evidence_node(deps))
    graph.add_node("generate_explanation", make_generate_explanation_node(deps))
    graph.add_edge(START, "build_evidence")
    graph.add_edge("build_evidence", "generate_explanation")
    graph.add_edge("generate_explanation", END)
    return cast(
        CompiledStateGraph[AgentState, None, AgentState, AgentState],
        graph.compile(name="explanation-subgraph"),
    )
