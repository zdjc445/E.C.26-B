"""记忆 recall / prepare / commit / turn summary 节点。"""

from __future__ import annotations

import json
from typing import Any

from shijiajing_agent.adapters.event_store import memory_event_attempt, stable_event_id
from shijiajing_agent.contracts import (
    AgentEventRecord,
    AgentExecutionContext,
    AgentResponse,
    AgentStatus,
    CompletionReason,
    ConversationTurnSummary,
    MemoryMutation,
    content_hash,
    now_iso,
)
from shijiajing_agent.domain.memory_policy import (
    build_memory_mutation,
    build_memory_query,
    validate_directive,
    validate_memory_directives,
)
from shijiajing_agent.nodes.node_support import timed
from shijiajing_agent.ports.dependencies import AgentDependenciesPort
from shijiajing_agent.state import AgentState


def _context(state: AgentState) -> AgentExecutionContext | None:
    value = state.get("execution_context")
    return value if isinstance(value, AgentExecutionContext) else None


def _enabled(state: AgentState, deps: AgentDependenciesPort) -> tuple[bool, str | None]:
    context = _context(state)
    if context is None or not context.memory_enabled or context.memory_owner_id is None:
        return False, None
    if deps.memory is None:
        return False, context.memory_owner_id
    return True, context.memory_owner_id


def _memory_flag(deps: AgentDependenciesPort, name: str, default: bool = True) -> bool:
    return bool(getattr(getattr(deps, "settings", None), name, default))


async def _record_memory_recalled(
    state: AgentState, deps: AgentDependenciesPort, *, count: int, status: str
) -> None:
    """记录记忆召回结果；不写 owner、查询或记忆值。"""
    if deps.event_store is None:
        return
    request = state["current_request"]
    try:
        await deps.event_store.append(
            AgentEventRecord(
                event_id=stable_event_id(
                    request.session_id,
                    request.request_id,
                    str(state.get("turn_id") or ""),
                    "memory",
                    "recall_memory",
                    "memory_recalled",
                    0,
                ),
                session_id=request.session_id,
                request_id=request.request_id,
                turn_id=str(state.get("turn_id") or ""),
                trace_id=str(state.get("trace_id") or ""),
                agent_name="memory",
                node_name="recall_memory",
                event_type="memory_recalled",
                status=status,
                payload={"count": count},
                occurred_at=now_iso(),
            )
        )
    except Exception:
        try:
            deps.metrics.inc("event_store_failure_total")
        except Exception:
            pass


def make_recall_memory_node(deps: AgentDependenciesPort) -> Any:
    @timed("recall_memory")
    async def recall_memory_node(state: AgentState) -> dict[str, Any]:
        enabled, owner_id = _enabled(state, deps)
        memory = deps.memory
        if (
            not enabled
            or owner_id is None
            or memory is None
            or not _memory_flag(deps, "memory_recall_enabled")
        ):
            return {"memory_context": []}
        try:
            query = build_memory_query(state, deps.settings.memory_recall_limit)
            memories = await memory.recall(owner_id, query)
            await _record_memory_recalled(state, deps, count=len(memories), status="success")
            return {"memory_context": memories}
        except Exception:
            await _record_memory_recalled(state, deps, count=0, status="failed")
            notices = list(state.get("notices") or [])
            notices.append("历史偏好读取失败，本轮未应用")
            return {
                "memory_context": [],
                "notices": notices,
            }

    return recall_memory_node


def make_prepare_memory_mutations_node(deps: AgentDependenciesPort) -> Any:
    @timed("prepare_memory_mutations")
    async def prepare_memory_mutations_node(state: AgentState) -> dict[str, Any]:
        enabled, owner_id = _enabled(state, deps)
        if not enabled or owner_id is None or not _memory_flag(deps, "memory_commit_enabled"):
            return {"pending_memory_mutations": []}
        patch = state.get("intent_patch")
        directives = list(getattr(patch, "memory_directives", []) or [])
        constraints = state.get("effective_constraints")
        current_category_id = (
            constraints.category_id.value
            if constraints is not None and constraints.category_id.value
            else None
        )
        directives = validate_memory_directives(
            directives,
            text=state["current_request"].text or "",
            taxonomy=deps.taxonomy,
            current_category_id=current_category_id,
        )
        if not directives:
            return {"pending_memory_mutations": []}
        request = state["current_request"]
        mutations: list[MemoryMutation] = []
        notices = list(state.get("notices") or [])
        for index, raw in enumerate(directives):
            try:
                directive = validate_directive(raw, deps.taxonomy)
                mutations.append(
                    build_memory_mutation(
                        owner_id,
                        request.session_id,
                        request.request_id,
                        index,
                        directive,
                    )
                )
            except Exception:
                notices.append("长期偏好指令未通过校验，本轮未保存")
        return {"pending_memory_mutations": mutations, "notices": notices}

    return prepare_memory_mutations_node


def make_commit_memory_node(deps: AgentDependenciesPort) -> Any:
    @timed("commit_memory")
    async def commit_memory_node(state: AgentState) -> dict[str, Any]:
        enabled, owner_id = _enabled(state, deps)
        memory = deps.memory
        mutations = list(state.get("pending_memory_mutations") or [])
        if (
            not enabled
            or owner_id is None
            or memory is None
            or not mutations
            or not _memory_flag(deps, "memory_commit_enabled")
        ):
            return {"pending_memory_mutations": []}
        try:
            records = await memory.commit(owner_id, mutations)
            if deps.event_store is not None:
                for mutation in mutations:
                    event_type = (
                        "memory_forgotten"
                        if mutation.operation.value in {"forget", "clear_owner"}
                        else "memory_committed"
                    )
                    try:
                        await deps.event_store.append(
                            AgentEventRecord(
                                event_id=stable_event_id(
                                    state["current_request"].session_id,
                                    state["current_request"].request_id,
                                    str(state.get("turn_id") or ""),
                                    "memory",
                                    "commit_memory",
                                    event_type,
                                    memory_event_attempt(mutation.mutation_id),
                                ),
                                session_id=state["current_request"].session_id,
                                request_id=state["current_request"].request_id,
                                turn_id=str(state.get("turn_id") or ""),
                                trace_id=str(state.get("trace_id") or ""),
                                agent_name="memory",
                                node_name="commit_memory",
                                event_type=event_type,
                                status="success",
                                output_hash=content_hash({"mutation_id": mutation.mutation_id}),
                                payload={
                                    "mutation_id": mutation.mutation_id,
                                    "operation": mutation.operation.value,
                                },
                                occurred_at=now_iso(),
                            )
                        )
                    except Exception:
                        try:
                            deps.metrics.inc("event_store_failure_total")
                        except Exception:
                            pass
            response = state.get("response")
            if isinstance(response, AgentResponse):
                notices = list(response.notices)
                if records:
                    notices.append("已按你的明确要求更新长期偏好")
                    response = response.model_copy(update={"notices": notices})
                    return {
                        "response": response,
                        "memory_context": records,
                        "pending_memory_mutations": [],
                        "memory_effects": [
                            {
                                "mutation_id": item.mutation_id,
                                "operation": item.operation.value,
                                "status": "committed",
                            }
                            for item in mutations
                        ],
                    }
            return {
                "memory_context": records,
                "pending_memory_mutations": [],
                "memory_effects": [
                    {
                        "mutation_id": item.mutation_id,
                        "operation": item.operation.value,
                        "status": "committed",
                    }
                    for item in mutations
                ],
            }
        except Exception:
            notices = list(state.get("notices") or [])
            notices.append("长期偏好保存失败，本轮结果未声明已记住")
            response = state.get("response")
            if isinstance(response, AgentResponse):
                response = response.model_copy(update={"notices": notices})
            return {
                "notices": notices,
                "response": response,
                "memory_effects": [
                    {
                        "mutation_id": item.mutation_id,
                        "operation": item.operation.value,
                        "status": "failed",
                    }
                    for item in mutations
                ],
            }

    return commit_memory_node


def append_turn_summary_node(
    state: AgentState, *, recent_turns_limit: int, recent_turns_max_bytes: int = 65_536
) -> dict[str, Any]:
    request = state["current_request"]
    response = state.get("response")
    reason = state.get("completion_reason")
    if reason is None and isinstance(response, AgentResponse):
        reason = {
            AgentStatus.SUCCESS: CompletionReason.SUCCESS,
            AgentStatus.CLARIFICATION: CompletionReason.CLARIFICATION,
            AgentStatus.NO_RESULTS: CompletionReason.NO_RESULTS,
            AgentStatus.FAILED: CompletionReason.FAILED,
        }[response.status]
    patch = state.get("intent_patch")
    safe_patch = _summary_intent_patch(patch)
    constraints = state.get("effective_constraints")
    category_id = (
        str(constraints.category_id.value)
        if constraints is not None and getattr(constraints.category_id, "value", None)
        else None
    )
    summary = ConversationTurnSummary(
        request_id=request.request_id,
        turn_id=str(state.get("turn_id") or ""),
        subject_id=state.get("subject_id"),
        category_id=category_id,
        constraint_delta=(safe_patch.model_dump(mode="json") if safe_patch is not None else {}),
        memory_effects=[
            {
                "mutation_id": str(effect.get("mutation_id") or ""),
                "operation": str(effect.get("operation") or ""),
                "status": str(effect.get("status") or ""),
            }
            for effect in list(state.get("memory_effects") or [])
            if effect.get("mutation_id")
        ],
        user_text=None,
        user_text_sha256=content_hash(request.text) if request.text is not None else None,
        user_text_length=len(request.text) if request.text is not None else None,
        # constraint_delta 是 recent-turns 的唯一意图投影；不保存模型原始 patch。
        intent_patch=None,
        completion_reason=reason,
        selected_group_ids=[
            item.group.group_id
            for item in (response.groups if isinstance(response, AgentResponse) else [])
        ],
        created_at=now_iso(),
    )
    turns = [*list(state.get("recent_turns") or []), summary][-recent_turns_limit:]
    while turns:
        encoded = json.dumps(
            [
                item.model_dump(mode="json") if hasattr(item, "model_dump") else item
                for item in turns
            ],
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        if len(encoded) <= recent_turns_max_bytes:
            break
        turns = turns[1:]
    return {"recent_turns": turns}


def _summary_intent_patch(patch: Any) -> Any:
    """只把可用于会话延续的白名单约束写入 recent_turns。"""
    if not hasattr(patch, "model_copy"):
        return None
    allowed = (
        "category_id",
        "min_price",
        "max_price",
        "colors",
        "platforms",
        "min_rating",
        "sort_by",
        "preferences",
        "cancelled_preferences",
        "clear_fields",
    )
    return patch.model_copy(
        update={
            name: getattr(patch, name, None) if name in allowed else None
            for name in type(patch).model_fields
            if name != "memory_directives"
        }
        | {"memory_directives": []}
    )
