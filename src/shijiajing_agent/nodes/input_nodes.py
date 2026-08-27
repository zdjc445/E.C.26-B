"""输入节点：校验、加载会话、准备主题。

- ``validate_input``：请求已在契约层校验，节点负责复制请求字段与标识。
- ``load_session``：从 Checkpoint 加载上一状态；无历史时创建新状态。
- ``prepare_subject``：新图片创建新 ``subject_id``；否则沿用历史（§7.4）。
"""

from __future__ import annotations

from typing import Any

from shijiajing_agent.contracts import AgentRequest
from shijiajing_agent.state import (
    DIRTY_FLAGS,
    SCHEMA_VERSION,
    AgentState,
    NativeTurnInput,
    new_state,
)


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

    上一轮未产出响应（进程中断）时标记 ``is_resumed`` 与
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
        "recent_turns": list(prev.get("recent_turns") or []),
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
        # 根图已完成 prepare_subject 时，RecognitionSubgraph 不能再次生成主题 ID。
        # 独立调用子图时 subject_id 为空，仍会在这里创建新主题。
        if state.get("subject_id") is not None:
            return {"subject_id": state.get("subject_id")}
        subject_id = f"sub:{uuid.uuid4().hex[:12]}"
        return {"subject_id": subject_id}
    if prev:
        return {"subject_id": prev.get("subject_id")}
    return {"subject_id": state.get("subject_id")}


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


def make_native_turn_input(req: AgentRequest) -> NativeTurnInput:
    """构造 native thread 的新 turn 增量，不把 previous_state 嵌套进 checkpoint。

    Native Checkpointer 会把输入增量合并到上一轮状态。这里显式重置本轮工作
    字段，避免旧响应、候选、查询和解释被下一轮复用；有效约束、识别历史、
    subject_id 与 recent_turns 不在增量中，按方案继续保留。
    """
    import uuid

    fresh = new_state(
        schema_version=SCHEMA_VERSION,
        session_id=req.session_id,
        request_id=req.request_id,
        turn_id=f"t:{uuid.uuid4().hex[:12]}",
        trace_id=f"tr:{uuid.uuid4().hex[:16]}",
        current_request=req,
    )
    fresh_values: dict[str, Any] = dict(fresh)
    return {
        "schema_version": SCHEMA_VERSION,
        "session_id": req.session_id,
        "request_id": req.request_id,
        "turn_id": fresh_values["turn_id"],
        "trace_id": fresh_values["trace_id"],
        "current_request": req,
        "previous_state": None,
        "image_ref": req.image,
        "selected_option_id": req.selected_option_id,
        # 新 turn 的工作记忆必须从 fresh defaults 开始。
        "intent_patch": fresh_values["intent_patch"],
        "conflicts": fresh_values["conflicts"],
        "retrieval_query": fresh_values["retrieval_query"],
        "candidates": fresh_values["candidates"],
        "retrieval_attempts": fresh_values["retrieval_attempts"],
        "retrieval_fallback_used": fresh_values["retrieval_fallback_used"],
        "relaxation_attempted": fresh_values["relaxation_attempted"],
        "relaxed_attributes": fresh_values["relaxed_attributes"],
        "normalized_candidates": fresh_values["normalized_candidates"],
        "spu_clusters": fresh_values["spu_clusters"],
        "same_item_review_pairs": fresh_values["same_item_review_pairs"],
        "sku_groups": fresh_values["sku_groups"],
        "ranked_groups": fresh_values["ranked_groups"],
        "clarification": fresh_values["clarification"],
        "evidence_bundle": fresh_values["evidence_bundle"],
        "explanation_text": fresh_values["explanation_text"],
        "explanation_verified": fresh_values["explanation_verified"],
        "response": fresh_values["response"],
        "memory_context": fresh_values["memory_context"],
        "memory_application": fresh_values["memory_application"],
        "ranking_context": fresh_values["ranking_context"],
        "dirty_flags": {name: True for name in DIRTY_FLAGS},
        "retry_counters": fresh_values["retry_counters"],
        "next_action": fresh_values["next_action"],
        "completion_reason": fresh_values["completion_reason"],
        "is_resumed": fresh_values["is_resumed"],
        "resumed_node": fresh_values["resumed_node"],
        "step_count": fresh_values["step_count"],
        "interrupt_generation": fresh_values["interrupt_generation"],
        "errors": fresh_values["errors"],
        "node_events": fresh_values["node_events"],
        "fallbacks": fresh_values["fallbacks"],
        "notices": fresh_values["notices"],
        "pending_memory_mutations": fresh_values["pending_memory_mutations"],
        "memory_effects": fresh_values["memory_effects"],
        "agent_results": fresh_values["agent_results"],
        "active_interrupt": fresh_values["active_interrupt"],
        "resume_consumed": fresh_values["resume_consumed"],
        "fusion_version": fresh_values["fusion_version"],
        "rerank_version": fresh_values["rerank_version"],
        "retrieval_index_version": fresh_values["retrieval_index_version"],
    }
