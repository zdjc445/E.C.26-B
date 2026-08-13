"""条件路由（方案 §9.1 主图分支）。全部为同步纯函数。"""

from __future__ import annotations

from shijiajing_agent.state import AgentState


def route_recognition(state: AgentState) -> str:
    """新图片 → recognize_image；否则（无图片）→ apply_correction。"""
    if state.get("image_ref") is not None:
        return "recognize_image"
    return "apply_correction"


def route_after_validation(state: AgentState) -> str:
    """冲突或缺少品类 → 澄清；否则 → 检索。"""
    if state.get("next_action") == "clarify":
        return "build_clarification"
    return "rewrite_query"


def route_retrieval(state: AgentState) -> str:
    """检索失败 → 直接失败；有候选 → 标准化；零结果 → 未放宽则放宽，已放宽 → 无结果。"""
    if state.get("next_action") == "failed":
        return "build_failed_response"
    if state.get("candidates"):
        return "normalize_candidates"
    if state.get("relaxation_attempted"):
        return "build_no_results"
    return "relax_recognition_constraints"


def route_after_relax(state: AgentState) -> str:
    """放宽后重查；无字段可放宽 → 无结果。"""
    if state.get("next_action") == "rewrite":
        return "rewrite_query"
    return "build_no_results"


def route_after_retrieval_failure(state: AgentState) -> str:
    """检索失败 → 直接失败。"""
    return "build_failed_response"
