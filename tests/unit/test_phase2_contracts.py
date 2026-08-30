"""HITL 外层契约测试。"""

import pytest

from shijiajing_agent.contracts import (
    ClarificationResume,
    MemoryConfirmationResume,
    RecognitionReviewResume,
    SameItemReviewResume,
)


def test_hitl_resume_models_are_kind_specific() -> None:
    assert ClarificationResume(action="select", option_id="cat:headphone")
    assert SameItemReviewResume(action="split")
    assert MemoryConfirmationResume(action="approve")
    with pytest.raises(ValueError):
        ClarificationResume(action="select")
    with pytest.raises(ValueError):
        RecognitionReviewResume(action="edit")
