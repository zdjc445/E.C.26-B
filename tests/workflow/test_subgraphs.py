"""专业子图的独立执行与根图装配回归。"""

from __future__ import annotations

from typing import Any

import pytest

from shijiajing_agent.config import Settings
from shijiajing_agent.contracts import (
    AgentRequest,
    ConstraintSource,
    ShoppingConstraints,
    SourcedValue,
)
from shijiajing_agent.graph import build_graph
from shijiajing_agent.nodes.input_nodes import make_initial_state
from shijiajing_agent.state import DIRTY_FLAGS, AgentState, NativeTurnInput
from shijiajing_agent.subgraphs import (
    build_explanation_subgraph,
    build_intent_subgraph,
    build_memory_subgraph,
    build_recognition_subgraph,
    build_retrieval_subgraph,
)

from .conftest import make_deps, make_image, two_candidate_result


def _request(*, text: str, image: Any = None) -> AgentRequest:
    return AgentRequest(session_id="subgraph-test", request_id="r1", text=text, image=image)


def test_root_graph_assembles_professional_subgraphs(
    taxonomy: Any,
) -> None:
    deps, _ = make_deps(taxonomy, Settings())
    graph = build_graph(deps)
    assert graph.builder.state_schema is AgentState
    assert graph.builder.input_schema is NativeTurnInput
    nodes = set(graph.get_graph().nodes)

    assert {
        "recognition_subgraph",
        "intent_subgraph",
        "retrieval_subgraph",
        "explanation_subgraph",
    } <= nodes


@pytest.mark.asyncio
async def test_each_professional_subgraph_executes_independently(taxonomy: Any) -> None:
    deps, fakes = make_deps(taxonomy, Settings())

    recognition_state = make_initial_state(
        _request(text="这是什么", image=make_image()),
        None,
    )
    recognition_state["image_ref"] = make_image()
    recognition = await build_recognition_subgraph(deps).ainvoke(recognition_state)
    assert recognition["recognition"].category_id == "headphone"
    assert recognition["recognition_id"] == "rec-1"

    intent = await build_intent_subgraph(deps).ainvoke(
        make_initial_state(_request(text="索尼耳机"), None)
    )
    assert intent["intent_patch"].category_id == "headphone"

    retrieval_state = make_initial_state(_request(text="索尼耳机"), None)
    retrieval_state["effective_constraints"] = ShoppingConstraints(
        category_id=SourcedValue(
            value="headphone",
            source=ConstraintSource.USER_TEXT,
            locked_by_user=True,
        )
    )
    retrieval_state["dirty_flags"] = {name: True for name in DIRTY_FLAGS}
    fakes["retrieval"].sequence = [two_candidate_result()]
    retrieval = await build_retrieval_subgraph(deps).ainvoke(retrieval_state)
    assert retrieval["retrieval_query"] is not None
    assert retrieval["candidates"]
    assert retrieval["normalized_candidates"]

    fakes["retrieval"].sequence = [two_candidate_result()]
    full_state = await build_graph(deps).ainvoke(
        make_initial_state(_request(text="索尼耳机"), None)
    )
    explanation = await build_explanation_subgraph(deps).ainvoke(full_state)
    assert explanation["evidence_bundle"] is not None
    assert explanation["explanation_text"]

    memory = await build_memory_subgraph(deps).ainvoke(
        make_initial_state(_request(text="索尼耳机"), None)
    )
    assert memory["memory_context"] == []
    assert memory["pending_memory_mutations"] == []
