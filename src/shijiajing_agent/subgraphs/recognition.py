"""RecognitionSubgraph：识别、用户修正和标准化。"""

from __future__ import annotations

from typing import Any, cast

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from shijiajing_agent.nodes.input_nodes import prepare_subject_node
from shijiajing_agent.nodes.recognition_nodes import (
    make_apply_correction_node,
    make_normalize_recognition_node,
    make_recognize_image_node,
)
from shijiajing_agent.ports.dependencies import AgentDependenciesPort
from shijiajing_agent.routing import route_recognition
from shijiajing_agent.state import AgentState


def build_recognition_subgraph(
    deps: AgentDependenciesPort,
) -> CompiledStateGraph[AgentState, None, AgentState, AgentState]:
    graph: Any = StateGraph(AgentState)
    graph.add_node("prepare_subject", prepare_subject_node)
    graph.add_node("recognize_image", make_recognize_image_node(deps))
    graph.add_node("apply_correction", make_apply_correction_node(deps))
    graph.add_node("normalize_recognition", make_normalize_recognition_node(deps))
    graph.add_edge(START, "prepare_subject")
    graph.add_conditional_edges(
        "prepare_subject",
        route_recognition,
        {"recognize_image": "recognize_image", "apply_correction": "apply_correction"},
    )
    graph.add_edge("recognize_image", "normalize_recognition")
    graph.add_edge("apply_correction", "normalize_recognition")
    graph.add_edge("normalize_recognition", END)
    return cast(
        CompiledStateGraph[AgentState, None, AgentState, AgentState],
        graph.compile(name="recognition-subgraph"),
    )
