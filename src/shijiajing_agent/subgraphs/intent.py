"""IntentSubgraph：当前轮结构化意图抽取。"""

from __future__ import annotations

from typing import Any, cast

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from shijiajing_agent.nodes.intent_nodes import make_parse_intent_node
from shijiajing_agent.ports.dependencies import AgentDependenciesPort
from shijiajing_agent.state import AgentState


def build_intent_subgraph(
    deps: AgentDependenciesPort,
) -> CompiledStateGraph[AgentState, None, AgentState, AgentState]:
    graph: Any = StateGraph(AgentState)
    graph.add_node("parse_intent", make_parse_intent_node(deps))
    graph.add_edge(START, "parse_intent")
    graph.add_edge("parse_intent", END)
    return cast(
        CompiledStateGraph[AgentState, None, AgentState, AgentState],
        graph.compile(name="intent-subgraph"),
    )
