"""输入节点：校验、加载会话、准备主题（方案 §9.2）。

- ``validate_input``：请求已在契约层校验，节点负责复制请求字段与标识。
- ``load_session``：从 Checkpoint 加载上一状态；无历史时创建新状态。
- ``prepare_subject``：新图片创建新 ``subject_id``；否则沿用历史（§7.4）。
"""

from __future__ import annotations

from typing import Any

from shijiajing_agent.contracts import AgentRequest
from shijiajing_agent.state import SCHEMA_VERSION, AgentState, new_state


def validate_input_node(state: AgentState) -> dict[str, Any]:
    """复制当前请求并生成唯一 turn_id（若缺失）。"""
    req: AgentRequest = state["current_request"]
    return {
        "session_id": req.session_id,
        "request_id": req.request_id,
        "image_ref": req.image,
        "selected_option_id": req.selected_option_id,
        "subject_id": None,
    }


def load_session_node(state: AgentState) -> dict[str, Any]:
    """从 previous_state 恢复历史；无历史时初始化新状态字段。

    §17.4：上一轮未产出响应（进程中断）时标记 ``is_resumed`` 与
    ``resumed_node``（上次成功完成的节点），供 trace 与恢复语义使用。
    """
    prev = state.get("previous_state")
    if prev is None:
        return {}
    prev_events = prev.get("node_events") or []
    resumed_node = prev_events[-1].get("node_name") if prev_events else None
    resuming = prev.get("response") is None
    delta: dict[str, Any] = {
        "recognition": prev.get("recognition"),
        "recognition_history": list(prev.get("recognition_history") or []),
        "recognition_id": prev.get("recognition_id"),
        "effective_constraints": prev.get("effective_constraints"),
        "state_version": prev.get("state_version", 0),
        "keywords": list(prev.get("keywords") or []),
        "retrieval_attempts": prev.get("retrieval_attempts", 0),
        "relaxation_attempted": prev.get("relaxation_attempted", False),
        "step_count": prev.get("step_count", 0),
        "is_resumed": resuming,
        "resumed_node": resumed_node if resuming else None,
        # 缓存结果：局部重算（§10）时未变化的阶段直接复用
        "retrieval_query": prev.get("retrieval_query"),
        "candidates": list(prev.get("candidates") or []),
        "normalized_candidates": list(prev.get("normalized_candidates") or []),
        "spu_clusters": list(prev.get("spu_clusters") or []),
        "sku_groups": list(prev.get("sku_groups") or []),
        "ranked_groups": list(prev.get("ranked_groups") or []),
        # response 幂等由 facade 在进入图前处理；图内始终从 None 构建
        "response": None,
    }
    return delta


def prepare_subject_node(state: AgentState) -> dict[str, Any]:
    """§7.4：新图片 → 新 subject_id；无新图片沿用历史。"""
    import uuid

    prev = state.get("previous_state")
    if state.get("image_ref") is not None:
        subject_id = f"sub:{uuid.uuid4().hex[:12]}"
        return {"subject_id": subject_id}
    if prev:
        return {"subject_id": prev.get("subject_id")}
    return {"subject_id": None}


def make_initial_state(req: AgentRequest, prev: AgentState | None) -> AgentState:
    """facade 使用的初始状态：注入 previous_state 供图内节点读取。"""
    import uuid

    state = new_state(
        schema_version=SCHEMA_VERSION,
        session_id=req.session_id,
        request_id=req.request_id,
        turn_id=f"t:{uuid.uuid4().hex[:12]}",
        trace_id=f"tr:{uuid.uuid4().hex[:16]}",
        current_request=req,
    )
    state["previous_state"] = prev
    return state
