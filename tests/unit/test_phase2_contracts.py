"""二期外层契约和独立子图装配测试。"""

from __future__ import annotations

import pytest

from shijiajing_agent.contracts import (
    ClarificationResume,
    MemoryConfirmationResume,
    RecognitionResult,
    RecognitionReviewResume,
    SameItemReviewResume,
)
from shijiajing_agent.graph import _make_subgraph_node
from shijiajing_agent.subgraphs import (
    IntentSubgraphOutput,
    RecognitionSubgraphOutput,
)


def test_hitl_resume_models_are_kind_specific() -> None:
    assert ClarificationResume(action="select", option_id="cat:headphone")
    assert SameItemReviewResume(action="split")
    assert MemoryConfirmationResume(action="approve")
    with pytest.raises(ValueError):
        ClarificationResume(action="select")
    with pytest.raises(ValueError):
        RecognitionReviewResume(action="edit")


def test_subgraph_outputs_validate_nested_domain_contracts() -> None:
    output = RecognitionSubgraphOutput.model_validate(
        {"recognition": {"recognition_id": "rec-1", "category_id": "headphone"}}
    )
    assert output.recognition is not None
    assert output.recognition.recognition_id == "rec-1"

    with pytest.raises(ValueError):
        RecognitionSubgraphOutput.model_validate(
            {
                "recognition": {
                    "recognition_id": "rec-1",
                    "unexpected_field": "must be rejected",
                }
            }
        )
    with pytest.raises(ValueError):
        IntentSubgraphOutput.model_validate({"intent_patch": {"unexpected_field": True}})


@pytest.mark.asyncio
async def test_subgraph_boundary_drops_unauthorized_root_fields() -> None:
    class FakeSubgraph:
        async def ainvoke(self, state: object) -> dict[str, object]:
            del state
            return {
                "schema_version": "must-not-cross-boundary",
                "recognition": RecognitionResult(recognition_id="rec-1"),
            }

    node = _make_subgraph_node(
        FakeSubgraph(), RecognitionSubgraphOutput, node_name="recognition_subgraph"
    )
    delta = await node({})
    assert "schema_version" not in delta
    assert delta["recognition"].recognition_id == "rec-1"


@pytest.mark.asyncio
async def test_subgraph_boundary_validation_failure_is_tagged() -> None:
    class InvalidSubgraph:
        async def ainvoke(self, state: object) -> dict[str, object]:
            del state
            return {
                "recognition": {
                    "recognition_id": "rec-1",
                    "unexpected_field": True,
                }
            }

    node = _make_subgraph_node(
        InvalidSubgraph(), RecognitionSubgraphOutput, node_name="recognition_subgraph"
    )
    with pytest.raises(ValueError) as raised:
        await node({})
    assert raised.value.node_name == "recognition_subgraph"
