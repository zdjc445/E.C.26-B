"""响应节点：澄清、无结果、证据、解释、响应组装。

- ``build_clarification``：模板生成，一次只问一个主问题（§16）。
- ``generate_explanation``：事实一致性校验失败 → 模板解释（§11.5）。
- ``build_response``：组装 §6.4 AgentResponse。
"""

from __future__ import annotations

import uuid
from dataclasses import asdict
from typing import Any

from shijiajing_agent.contracts import AgentResponse, AgentStatus, ShoppingConstraints
from shijiajing_agent.domain.cache_policy import safe_get, safe_set, versioned_key
from shijiajing_agent.domain.constraints import ClarificationBuilder, ConstraintConflict
from shijiajing_agent.domain.evidence import EvidenceBuilder, FactualConsistencyChecker
from shijiajing_agent.nodes.node_support import record_cache_event, timed
from shijiajing_agent.ports.dependencies import AgentDependenciesPort
from shijiajing_agent.ports.models import ExplanationModelPort
from shijiajing_agent.state import AgentState, ErrorRecord


def make_build_clarification_node(deps: AgentDependenciesPort) -> Any:
    """澄清构建（§16）：冲突 → CONFLICT；缺品类 → MISSING_CATEGORY。"""

    @timed("build_clarification")
    async def build_clarification_node(state: AgentState) -> dict[str, Any]:
        constraints = state.get("effective_constraints")
        conflicts = state.get("conflicts") or []
        missing_category = constraints is None or constraints.category_id.value is None
        reason = "IDENTITY_MISSING"
        if conflicts:
            reason = "CONFLICT"
        elif missing_category:
            reason = "MISSING_CATEGORY"
        clarification = ClarificationBuilder().build(
            question_id=f"q:{uuid.uuid4().hex[:12]}",
            subject_id=state.get("subject_id") or "",
            turn_id=str(state.get("turn_id", "")),
            reason_code=reason,
            conflict=ConstraintConflict(**conflicts[0]) if conflicts else None,
            taxonomy=deps.taxonomy,
        )
        return {
            "clarification": clarification,
            "next_action": "clarification",
            "completion_reason": "clarification",
        }

    return build_clarification_node


def make_build_no_results_node(deps: AgentDependenciesPort) -> Any:
    """无结果响应（§9.3 no_results）。"""

    @timed("build_no_results")
    async def build_no_results_node(state: AgentState) -> dict[str, Any]:
        return {"next_action": "no_results", "completion_reason": "no_results"}

    return build_no_results_node


def make_build_evidence_node(deps: AgentDependenciesPort) -> Any:
    """事实证据构建（§11.5）。"""

    @timed("build_evidence")
    async def build_evidence_node(state: AgentState) -> dict[str, Any]:
        ranked = state.get("ranked_groups") or []
        constraints = state.get("effective_constraints") or ShoppingConstraints()
        bundle = EvidenceBuilder().build(ranked, constraints, notices=state.get("notices") or [])
        return {"evidence_bundle": bundle, "next_action": "evidence_ready"}

    return build_evidence_node


def make_generate_explanation_node(deps: AgentDependenciesPort) -> Any:
    """结果解释（§11.5）。模型失败或事实校验失败 → 模板解释。"""

    explanation_model: ExplanationModelPort = deps.explanation

    @timed("generate_explanation")
    async def generate_explanation_node(state: AgentState) -> dict[str, Any]:
        bundle = state.get("evidence_bundle")
        if bundle is None or not bundle.groups:
            return {"next_action": "explanation_ready"}
        checker = FactualConsistencyChecker()
        text = None
        verified = False
        fallback_used = False
        cache_key = versioned_key(
            {"evidence": asdict(bundle)},
            {"model": deps.settings.ark_text_model, "prompt": "v1"},
        )
        try:
            cached = await safe_get(deps.cache, "explanation", cache_key, metrics=deps.metrics)
            cached_text = None
            if isinstance(cached, dict) and isinstance(cached.get("explanation_text"), str):
                candidate = cached["explanation_text"]
                if bool(cached.get("verified")) and checker.verify(candidate, bundle)[0]:
                    cached_text = candidate
            await record_cache_event(
                deps,
                state,
                node_name="generate_explanation",
                namespace="explanation",
                cache_key=cache_key,
                hit=cached_text is not None,
            )
            if cached_text is not None:
                text = cached_text
                verified = True
            else:
                candidate = await explanation_model.explain(bundle)
                ok, _violations = checker.verify(candidate, bundle)
                if ok:
                    text = candidate
                    verified = True
                    await safe_set(
                        deps.cache,
                        "explanation",
                        cache_key,
                        {"explanation_text": candidate, "verified": True},
                        deps.settings.explanation_cache_ttl_seconds,
                        metrics=deps.metrics,
                    )
                else:
                    fallback_used = True
        except Exception:
            fallback_used = True
        if text is None:
            text = checker.template_explanation(bundle)
        delta: dict[str, Any] = {
            "explanation_text": text,
            "explanation_verified": verified,
            "next_action": "explanation_ready",
        }
        if fallback_used:
            delta["notices"] = [
                *list(state.get("notices") or []),
                "解释模型不可用或输出未通过事实校验，已使用模板解释",
            ]
            delta["fallbacks"] = [
                *list(state.get("fallbacks") or []),
                {
                    "node_name": "generate_explanation",
                    "reason": "factual_check_failed",
                    "fallback_provider": "template",
                },
            ]
        return delta

    return generate_explanation_node


def make_build_failed_node(deps: AgentDependenciesPort) -> Any:
    """确定性失败响应（§9.3 failed）：保留 trace，不把部分结果标记为成功。"""

    @timed("build_failed_response")
    async def build_failed_response_node(state: AgentState) -> dict[str, Any]:
        req = state["current_request"]
        errors = list(state.get("errors") or [])
        last = errors[-1] if errors else ErrorRecord()
        code = str(last.get("error_code") or "INTERNAL_ERROR")
        from shijiajing_agent.errors import ErrorCode

        if code == ErrorCode.RETRIEVAL_UNAVAILABLE.value:
            user_message = "检索服务不可用，请稍后重试。"
        elif code == ErrorCode.CHECKPOINT_UNAVAILABLE.value:
            user_message = "状态存储不可用，请稍后重试。"
        else:
            user_message = "处理失败，请稍后重试。"
        response = AgentResponse(
            session_id=req.session_id,
            request_id=req.request_id,
            turn_id=str(state.get("turn_id", "")),
            status=AgentStatus.FAILED,
            message=user_message,
            recognition=state.get("recognition"),
            effective_constraints=state.get("effective_constraints"),
            notices=state.get("notices") or [],
            trace_id=str(state.get("trace_id", "")),
        )
        return {
            "response": response,
            "next_action": "response_built",
            "completion_reason": "failed",
        }

    return build_failed_response_node


def _summary_message(state: AgentState, status: AgentStatus) -> str:
    text = state.get("explanation_text")
    if text:
        return text
    if status == AgentStatus.CLARIFICATION:
        return "需要补充信息后继续比价。"
    if status == AgentStatus.NO_RESULTS:
        return "当前条件下没有符合要求的比价结果。"
    return "已为您完成比价。"


def make_build_response_node(deps: AgentDependenciesPort) -> Any:
    """组装 AgentResponse（§6.4）。"""

    @timed("build_response")
    async def build_response_node(state: AgentState) -> dict[str, Any]:
        req = state["current_request"]
        status = {
            "clarification": AgentStatus.CLARIFICATION,
            "no_results": AgentStatus.NO_RESULTS,
            "success": AgentStatus.SUCCESS,
        }.get(state.get("next_action", ""), AgentStatus.SUCCESS)
        if status == AgentStatus.SUCCESS and not (state.get("ranked_groups") or []):
            status = AgentStatus.NO_RESULTS
        ranked = state.get("ranked_groups") or []
        if state.get("explanation_text"):
            for rg in ranked:
                rg.explanation = state.get("explanation_text")
                rg.explanation_verified = bool(state.get("explanation_verified"))
        response = AgentResponse(
            session_id=req.session_id,
            request_id=req.request_id,
            turn_id=str(state.get("turn_id", "")),
            status=status,
            message=_summary_message(state, status),
            recognition=state.get("recognition"),
            effective_constraints=state.get("effective_constraints"),
            groups=ranked,
            clarification=state.get("clarification"),
            notices=state.get("notices") or [],
            trace_id=str(state.get("trace_id", "")),
        )
        return {
            "response": response,
            "next_action": "response_built",
            "completion_reason": status.value,
        }

    return build_response_node
