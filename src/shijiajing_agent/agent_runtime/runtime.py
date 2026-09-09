"""主 Agent 的受控 observe → decide → act → observe 循环。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from time import perf_counter
from typing import Any, cast

from shijiajing_agent.agent_runtime.budget import BudgetExceededError, BudgetLedger
from shijiajing_agent.agent_runtime.checkpoint import AgentRuntimeCheckpointPort
from shijiajing_agent.agent_runtime.contracts import (
    ActionRecord,
    ActionStatus,
    AgentRuntimeUsage,
    AnswerAction,
    AskUserAction,
    DelegateResearchAction,
    DelegateVerificationAction,
    InspectEvidenceAction,
    MainAction,
    MainRuntimeState,
    RuntimeBudget,
    RuntimeSessionSnapshot,
    SearchAndCompareAction,
    SubagentBudget,
    SubagentResult,
    SubagentRole,
    SubagentStatus,
    SubagentTask,
    SupplementSearchAction,
    ToolObservation,
)
from shijiajing_agent.agent_runtime.main_agent import MainAgent
from shijiajing_agent.agent_runtime.policy import (
    ActionGuard,
    ActionRejectedError,
    DelegationPolicy,
    FallbackPolicy,
    allowed_actions_for,
    observation_for,
)
from shijiajing_agent.agent_runtime.subagents.research import ResearchSubagent
from shijiajing_agent.agent_runtime.subagents.verification import VerificationSubagent
from shijiajing_agent.contracts import (
    AgentExecutionContext,
    AgentInterrupt,
    AgentRequest,
    AgentResponse,
    AgentResume,
    AgentStatus,
    AgentTurnResult,
    CanonicalUnderstanding,
    Clarification,
    CompletionReason,
    ConversationTurnSummary,
    InterruptKind,
    MemoryConfirmationResume,
    RecognitionReviewResume,
    RetrievalCandidate,
    SameItemReviewResume,
    ShoppingConstraints,
    content_hash,
    now_iso,
)
from shijiajing_agent.domain.candidate_selection import select_candidate_window
from shijiajing_agent.domain.constraints import ConstraintMerger
from shijiajing_agent.domain.filters import HardFilterBuilder
from shijiajing_agent.domain.memory_policy import (
    apply_memory_defaults,
    build_memory_query,
    memory_authorization_id,
    resolve_memory_application,
)
from shijiajing_agent.services.answer import AnswerService
from shijiajing_agent.services.comparison import ComparisonService
from shijiajing_agent.services.evidence import EvidenceService
from shijiajing_agent.services.intent import IntentService
from shijiajing_agent.services.memory import MemoryService
from shijiajing_agent.services.recognition import RecognitionService
from shijiajing_agent.services.retrieval import RetrievalService


@dataclass(frozen=True)
class MainAgentRunResult:
    state: MainRuntimeState
    response: AgentResponse
    interrupt: AgentInterrupt | None = None


@dataclass(frozen=True)
class _StagedCandidateEvaluation:
    recall_pool: list[RetrievalCandidate]
    window: list[RetrievalCandidate]
    comparison: Any
    evidence_records: list[Any]
    assessment: dict[str, Any] | None
    gaps: list[str]
    conflicts: list[str]
    notices: list[str]


class MainAgentRuntime:
    """一个请求只创建一个主 Agent；每次重新决策仍属于同一个 runtime。"""

    engine_version = "main-agent-runtime-v2"

    def __init__(
        self,
        deps: Any,
        *,
        decision_port: Any | None = None,
        checkpoint: AgentRuntimeCheckpointPort | None = None,
    ) -> None:
        self._deps = deps
        self._settings = deps.settings
        self._checkpoint = checkpoint
        self._decision_port = decision_port or getattr(deps, "agent_decision", None)
        if self._decision_port is None:
            raise ValueError("Main Agent 未注入 AgentDecisionPort")
        categories = {
            category.category_id: category.category_name for category in deps.taxonomy.categories()
        }
        comparison = ComparisonService(
            deps.taxonomy,
            accept_threshold=deps.settings.same_item_accept_threshold,
            review_threshold=deps.settings.same_item_review_threshold,
            preference_weights=deps.settings.preference_weights,
            schema_inducer=getattr(deps, "dynamic_schema_inducer", None),
            canonicalizer=getattr(deps, "dynamic_product_canonicalizer", None),
            cache=getattr(deps, "cache", None),
            metrics=deps.metrics,
            schema_batch_size=deps.settings.dynamic_schema_batch_size,
            canonicalization_batch_size=deps.settings.dynamic_canonicalization_batch_size,
            concept_min_confidence=deps.settings.dynamic_schema_concept_min_confidence,
            role_min_confidence=deps.settings.dynamic_schema_role_min_confidence,
            role_min_support=deps.settings.dynamic_schema_role_min_support,
            max_concepts=deps.settings.dynamic_schema_max_concepts,
            max_attributes_per_concept=deps.settings.dynamic_schema_max_attributes_per_concept,
            field_min_confidence=deps.settings.dynamic_canonicalization_field_min_confidence,
            cache_ttl_seconds=deps.settings.dynamic_schema_cache_ttl_seconds,
        )
        self._recognition = RecognitionService(
            deps.vision, deps.taxonomy, deps.settings.recognition_review_threshold
        )
        self._intent = IntentService(deps.intent, deps.taxonomy)
        self._retrieval = RetrievalService(
            deps.query_rewrite,
            deps.retrieval,
            comparison,
            category_names=categories,
            top_k=deps.settings.retrieval_top_k_per_channel,
            union_limit=deps.settings.retrieval_union_limit,
            candidate_window_limit=deps.settings.matching_candidate_limit,
            rrf_k=deps.settings.retrieval_rrf_k,
            initial_max_queries=deps.settings.retrieval_initial_max_queries,
            query_concurrency=deps.settings.retrieval_query_concurrency,
        )
        self._evidence = EvidenceService()
        self._answer = AnswerService(self._evidence, deps.explanation)
        self._memory = MemoryService(getattr(deps, "memory", None), deps.taxonomy)
        self._main_agent = MainAgent(self._decision_port)
        research_decision = getattr(deps, "research_decision", None)
        self._research = (
            ResearchSubagent(
                research_decision,
                self._retrieval,
                self._evidence,
                max_queries=deps.settings.retrieval_supplement_max_queries,
            )
            if research_decision is not None
            else None
        )
        verification_decision = getattr(deps, "verification_decision", None)
        offer_details = getattr(deps, "offer_details", None)
        self._verification = (
            VerificationSubagent(
                verification_decision,
                offer_details,
                self._retrieval,
                self._evidence,
            )
            if verification_decision is not None and offer_details is not None
            else None
        )
        self._guard = ActionGuard(
            DelegationPolicy(
                research_enabled=self._research is not None,
                verification_enabled=self._verification is not None,
                offer_details=offer_details,
            )
        )
        self._fallback = FallbackPolicy()
        self._local_states: dict[tuple[str, str], MainRuntimeState] = {}
        self._local_sessions: dict[str, RuntimeSessionSnapshot] = {}

    async def run(
        self,
        request: AgentRequest,
        *,
        context: AgentExecutionContext | None = None,
        pause_for_hitl: bool = False,
        suppress_side_effects: bool = False,
        resume: AgentResume | None = None,
    ) -> MainAgentRunResult:
        context = context or AgentExecutionContext()
        state, checkpoint_version = await self._load_or_initialize(request, context)
        if state.final_response is not None and resume is None:
            return MainAgentRunResult(state, state.final_response)
        if state.active_interrupt is not None and resume is None:
            return MainAgentRunResult(
                state,
                self._interrupt_response(state, state.active_interrupt),
                state.active_interrupt,
            )
        if resume is not None:
            response = await self._apply_resume(
                state,
                resume,
                context,
                suppress_side_effects=suppress_side_effects,
            )
            if response is not None:
                await self._save(state, checkpoint_version)
                return MainAgentRunResult(state, response)
            state.active_interrupt = None
            await self._save(state, checkpoint_version)
            checkpoint_version = await self._checkpoint_version(state)

        if (
            pause_for_hitl
            and self._settings.hitl_enabled
            and state.understanding.recognition is not None
            and state.understanding.recognition.overall_confidence
            < self._settings.recognition_review_threshold
            and "recognition_review" not in state.completed_interrupts
        ):
            interrupt = self._make_interrupt(
                state,
                InterruptKind.RECOGNITION_REVIEW,
                "图片识别置信度较低，请确认或修正识别结果。",
                {
                    "recognition": state.understanding.recognition.model_dump(mode="json"),
                },
            )
            state.active_interrupt = interrupt
            await self._save(state, checkpoint_version)
            return MainAgentRunResult(state, self._interrupt_response(state, interrupt), interrupt)

        invalid_actions = 0
        started = perf_counter()
        while True:
            ledger = BudgetLedger.start(state.budget, state.usage)
            if not ledger.can_decide() or not ledger.can_model():
                return await self._terminal(
                    state,
                    context,
                    suppress_side_effects=suppress_side_effects,
                    reason="budget_exhausted",
                )
            allowed = allowed_actions_for(
                state,
                research_enabled=self._research is not None,
                verification_enabled=self._verification is not None,
            )
            observation = observation_for(state, allowed)
            try:
                decision = await self._main_agent.decide(observation, allowed)
                state.usage = state.usage.add(
                    decision.usage.model_copy(
                        update={
                            "decisions": max(1, decision.usage.decisions),
                            "model_calls": max(1, decision.usage.model_calls),
                        }
                    )
                )
                self._ensure_within_budget(state)
                self._guard.validate(decision.action, state, allowed_actions=allowed)
            except (ActionRejectedError, ValueError) as exc:
                invalid_actions += 1
                state.gaps = [f"invalid_action:{str(exc)[:80]}"]
                if invalid_actions >= 2:
                    return await self._terminal(
                        state,
                        context,
                        suppress_side_effects=suppress_side_effects,
                        reason="invalid_action_limit",
                    )
                continue
            except BudgetExceededError:
                return await self._terminal(
                    state,
                    context,
                    suppress_side_effects=suppress_side_effects,
                    reason="budget_exhausted",
                )

            invalid_actions = 0
            action = decision.action
            fingerprint = content_hash(
                {
                    "action": action.model_dump(mode="json"),
                    "constraints_version": state.constraints_version,
                    "evidence_version": state.evidence_version,
                }
            )
            record = ActionRecord(
                action_id=self._action_id(state, action, fingerprint),
                agent_id="main",
                kind=action.kind,
                input_fingerprint=fingerprint,
                constraints_version=state.constraints_version,
                evidence_version=state.evidence_version,
            )
            state.actions.append(record)
            record_index = len(state.actions) - 1
            if fingerprint in state.seen_fingerprints:
                state.no_progress_count += 1
                state.actions[record_index] = record.model_copy(
                    update={"status": ActionStatus.FAILED, "error_code": "DUPLICATE_ACTION"}
                )
                if state.no_progress_count >= 2:
                    return await self._terminal(
                        state,
                        context,
                        suppress_side_effects=suppress_side_effects,
                        reason="no_progress",
                    )
                continue
            state.seen_fingerprints.append(fingerprint)
            state.actions[record_index] = record.model_copy(update={"status": ActionStatus.RUNNING})
            await self._save(state, checkpoint_version)
            checkpoint_version = await self._checkpoint_version(state)
            action_started = perf_counter()
            try:
                tool, response, interrupt = await self._execute_action(
                    state,
                    action,
                    context,
                    pause_for_hitl=pause_for_hitl,
                    suppress_side_effects=suppress_side_effects,
                )
                if tool is not None:
                    self._add_usage(state, tool.usage)
                    state.last_tool_status = tool.status
                    state.actions[record_index] = record.model_copy(
                        update={
                            "status": ActionStatus.COMPLETED,
                            "result_refs": tool.result_refs,
                            "usage": tool.usage,
                        }
                    )
                else:
                    state.actions[record_index] = record.model_copy(
                        update={
                            "status": ActionStatus.COMPLETED,
                            "usage": AgentRuntimeUsage(
                                elapsed_ms=(perf_counter() - action_started) * 1000
                            ),
                        }
                    )
                state.usage = state.usage.model_copy(
                    update={
                        "elapsed_ms": state.usage.elapsed_ms + (perf_counter() - started) * 1000
                    }
                )
            except BudgetExceededError:
                state.actions[record_index] = record.model_copy(
                    update={"status": ActionStatus.FAILED, "error_code": "BUDGET_EXCEEDED"}
                )
                return await self._terminal(
                    state,
                    context,
                    suppress_side_effects=suppress_side_effects,
                    reason="budget_exhausted",
                )
            except Exception:
                state.actions[record_index] = record.model_copy(
                    update={"status": ActionStatus.FAILED, "error_code": "ACTION_FAILED"}
                )
                state.last_tool_status = "failed"
                state.gaps = ["action_failed"]
                continue
            await self._save(state, checkpoint_version)
            checkpoint_version = await self._checkpoint_version(state)
            if interrupt is not None:
                return MainAgentRunResult(
                    state, self._interrupt_response(state, interrupt), interrupt
                )
            if response is not None:
                state.final_response = response
                await self._save_session(state)
                await self._save(state, checkpoint_version)
                return MainAgentRunResult(state, response)

    async def resume(
        self,
        session_id: str,
        resume: AgentResume,
        context: AgentExecutionContext,
        *,
        suppress_side_effects: bool = False,
    ) -> AgentTurnResult:
        active = await self._load_active(session_id)
        if active is None:
            return AgentTurnResult(
                response=AgentResponse(
                    session_id=session_id,
                    request_id="resume",
                    turn_id="resume",
                    status=AgentStatus.FAILED,
                    message="当前 session 没有待恢复的 Agent runtime interrupt。",
                    trace_id="resume",
                )
            )
        _, state, _ = active
        result = await self.run(
            state.current_request,
            context=context,
            pause_for_hitl=True,
            suppress_side_effects=suppress_side_effects,
            resume=resume,
        )
        if result.interrupt is not None:
            return AgentTurnResult(interrupt=result.interrupt)
        return AgentTurnResult(response=result.response)

    async def _load_or_initialize(
        self, request: AgentRequest, context: AgentExecutionContext
    ) -> tuple[MainRuntimeState, int | None]:
        key = (request.session_id, request.request_id)
        if self._checkpoint is not None:
            loaded = await self._checkpoint.load_request(*key)
            if loaded is not None:
                return loaded
        local = self._local_states.get(key)
        if local is not None:
            return local.model_copy(deep=True), None
        snapshot = await self._load_session(request.session_id)
        state = MainRuntimeState(
            session_id=request.session_id,
            request_id=request.request_id,
            turn_id=f"turn:{request.request_id}",
            trace_id=f"trace:{request.request_id}",
            engine_version=self.engine_version,
            current_request=request,
            context={"memory_enabled": context.memory_enabled},
            budget=RuntimeBudget(
                max_decisions=self._settings.main_agent_max_decisions,
                max_tool_calls=self._settings.main_agent_max_tool_calls,
                max_retrieval_calls=self._settings.main_agent_max_retrieval_calls,
                max_model_calls=self._settings.main_agent_max_model_calls,
                max_tokens=self._settings.main_agent_max_tokens,
                max_subagent_starts=self._settings.main_agent_max_subagent_starts,
                max_seconds=self._settings.turn_timeout_seconds,
            ),
        )
        await self._prepare(
            state,
            context,
            previous_constraints=snapshot.constraints if snapshot is not None else None,
            previous_recognition=snapshot.recognition if snapshot is not None else None,
            recent_turns=self._recent_turns(snapshot),
            reset_results=False,
        )
        self._local_states[key] = state.model_copy(deep=True)
        return state, None

    async def _prepare(
        self,
        state: MainRuntimeState,
        context: AgentExecutionContext,
        *,
        previous_constraints: ShoppingConstraints | None,
        previous_recognition: Any | None,
        recent_turns: list[ConversationTurnSummary],
        reset_results: bool,
    ) -> None:
        request = state.current_request
        if reset_results:
            state.ranked_groups = []
            state.last_candidates = []
            state.retrieval_assessment = None
            state.evidence = {}
            state.evidence_version = 0
        recognition_outcome = await self._recognition.run(
            image=request.image,
            correction=request.correction,
            previous=previous_recognition,
        )
        intent_outcome = await self._intent.run(
            request.text or request.selected_option_id,
            previous_constraints,
            recent_turns=recent_turns,
        )
        self._add_usage(
            state,
            AgentRuntimeUsage(
                model_calls=recognition_outcome.model_calls + intent_outcome.model_calls
            ),
        )
        memories = []
        if (
            context.memory_enabled
            and context.memory_owner_id
            and self._settings.memory_recall_enabled
        ):
            try:
                query = build_memory_query(
                    {"effective_constraints": previous_constraints},
                    self._settings.memory_recall_limit,
                )
                memories = await self._memory.recall(context.memory_owner_id, query)
            except Exception:
                state.notices.append("历史偏好读取失败，本轮未应用")
        merged = ConstraintMerger(self._deps.taxonomy).merge(
            prev=previous_constraints,
            vision=recognition_outcome.recognition,
            intent=intent_outcome.patch,
            correction=request.correction,
            new_subject=request.image is not None,
            turn_id=state.turn_id,
        )
        application = resolve_memory_application(merged.constraints, memories)
        constraints = apply_memory_defaults(merged.constraints, memories)
        constraints_changed = (
            state.understanding.constraints is not None
            and previous_constraints is not None
            and constraints != previous_constraints
        )
        state.understanding = CanonicalUnderstanding(
            recognition=recognition_outcome.recognition,
            intent_patch=intent_outcome.patch,
            constraints=constraints,
            memory_records=memories,
            memory_application=application,
        )
        if constraints_changed:
            state.constraints_version += 1
        if reset_results or constraints_changed:
            state.supplement_stage_used = False
            state.supplement_query_fingerprints = []
            state.supplement_no_progress_count = 0
        if reset_results:
            state.recall_pool = []
        if reset_results or constraints_changed:
            state.retrieval_assessment = None
        state.gaps = []
        if not constraints.category_id.value:
            state.gaps.append("missing_category")
        state.conflicts = [item.message for item in merged.conflicts]
        if merged.notices:
            state.notices.extend(merged.notices)
        if recognition_outcome.fallback_reason and (
            request.image is not None or request.correction is not None
        ):
            state.notices.append("图片识别不可用，可继续文字理解")
        if intent_outcome.fallback_reason:
            state.notices.append("意图模型不可用，已使用规则解析")
        if context.memory_enabled and context.memory_owner_id and state.understanding.intent_patch:
            state.pending_mutations = self._memory.prepare(
                context.memory_owner_id,
                state.session_id,
                state.request_id,
                state.understanding.intent_patch.memory_directives,
            )
        state.memory_authorized = not (
            self._settings.hitl_enabled and self._settings.memory_confirmation_required
        )

    async def _execute_action(
        self,
        state: MainRuntimeState,
        action: MainAction,
        context: AgentExecutionContext,
        *,
        pause_for_hitl: bool,
        suppress_side_effects: bool,
    ) -> tuple[ToolObservation | None, AgentResponse | None, AgentInterrupt | None]:
        constraints = state.understanding.constraints
        if isinstance(action, SearchAndCompareAction):
            assert constraints is not None
            if not BudgetLedger.start(state.budget, state.usage).can_retrieve():
                raise BudgetExceededError("真实检索次数超限")
            result = await self._retrieval.search_and_compare(
                action.query_text or state.current_request.text or "",
                constraints,
                recognition=state.understanding.recognition,
                image=state.current_request.image,
                soft_terms=action.soft_terms,
                constraints_version=state.constraints_version,
            )
            pool = list(result.search.retrieval.candidates or result.search.candidates)
            prepared_queries = (
                [result.search.plan.original_query, *result.search.plan.variants]
                if result.search.plan is not None
                else []
            )
            staged = await self._stage_candidate_evaluation(
                pool,
                constraints,
                comparison=result.comparison,
                query_fingerprints=[item.fingerprint for item in prepared_queries],
                query_assumptions=(
                    [assumption for item in prepared_queries for assumption in item.assumptions]
                ),
                retrieval_metadata={
                    "channel_health": {
                        key: value.value
                        for key, value in result.search.retrieval.channel_health.items()
                    },
                    "fallback_used": result.search.retrieval.fallback_used,
                    "index_version": result.search.retrieval.index_version,
                },
                stage="initial",
            )
            usage = result.usage.model_copy(update={"tool_calls": max(1, result.usage.tool_calls)})
            self._ensure_usage_delta(state, usage)
            previous_ids = {item.offer.offer_id for item in state.recall_pool}
            new_records = self._commit_staged_evaluation(state, staged)
            current_ids = {item.offer.offer_id for item in state.recall_pool}
            if new_records or previous_ids != current_ids:
                state.no_progress_count = 0
            elif previous_ids:
                state.no_progress_count += 1
            state.query_fingerprints = list(
                dict.fromkeys(
                    [*state.query_fingerprints, *[item.fingerprint for item in prepared_queries]]
                )
            )
            observation = ToolObservation(
                status=(
                    "no_results"
                    if not state.ranked_groups
                    else "fallback"
                    if result.comparison.fallback_used or result.search.retrieval.fallback_used
                    else "success"
                ),
                result_refs=[group.group.group_id for group in state.ranked_groups][:50],
                new_evidence_ids=[item.evidence_id for item in new_records][:50],
                gaps=list(state.gaps),
                conflicts=list(state.conflicts),
                fallback_reason=(
                    "retrieval_fallback"
                    if result.search.retrieval.fallback_used or result.comparison.fallback_used
                    else None
                ),
                constraints_version=state.constraints_version,
                evidence_version=state.evidence_version,
                usage=usage,
            )
            return observation, None, None
        if isinstance(action, SupplementSearchAction):
            assert constraints is not None
            max_queries = min(
                self._settings.retrieval_supplement_max_queries,
                len(action.query_proposals),
            )
            if max_queries < 1:
                raise ActionRejectedError("补查没有可执行查询")
            proposals = action.query_proposals[:max_queries]
            prepared = self._retrieval.prepare_explicit_queries(
                [item.text for item in proposals],
                constraints,
                constraints_version=state.constraints_version,
                assumptions_by_query=[list(item.assumptions) for item in proposals],
                evidence_refs_by_query=[list(item.evidence_refs) for item in proposals],
                image_sha256=(
                    state.current_request.image.sha256
                    if state.current_request.image is not None
                    else None
                ),
            )
            if not prepared:
                raise ActionRejectedError("补查查询为空或全部重复")
            expected_filters = HardFilterBuilder().build(constraints)
            invalid = [
                item
                for item in prepared
                if item.constraints_version != state.constraints_version
                or item.hard_filters.model_dump(mode="json")
                != expected_filters.model_dump(mode="json")
                or item.fingerprint in state.query_fingerprints
            ]
            if invalid:
                raise ActionRejectedError("补查查询重复或未绑定当前硬约束")
            if len(prepared) > state.budget.max_retrieval_calls - state.usage.retrieval_calls:
                raise BudgetExceededError("补查查询超过剩余检索预算")
            results = await self._retrieval.execute_prepared_query_batch(
                prepared,
                image=state.current_request.image,
            )
            merged_result = self._retrieval.merge_prepared_query_results(prepared, results)
            incoming = list(merged_result.candidates)
            previous_pool = list(state.recall_pool or state.last_candidates)
            merged_pool = self._retrieval.merge_candidate_pools(
                previous_pool,
                incoming,
                union_limit=self._settings.retrieval_union_limit,
            )
            staged = await self._stage_candidate_evaluation(
                merged_pool,
                constraints,
                query_fingerprints=[item.fingerprint for item in prepared],
                query_assumptions=[
                    assumption for item in prepared for assumption in item.assumptions
                ],
                retrieval_metadata={
                    "channel_health": {
                        key: value.value for key, value in merged_result.channel_health.items()
                    },
                    "fallback_used": merged_result.fallback_used,
                    "index_version": merged_result.index_version,
                },
                stage="supplement",
            )
            previous_offer_ids = {item.offer.offer_id for item in previous_pool}
            incoming_offer_ids = {item.offer.offer_id for item in incoming}
            new_offer_ids = incoming_offer_ids - previous_offer_ids
            previous_group_offer_ids = {
                offer.offer_id for group in state.ranked_groups for offer in group.group.offers
            }
            current_group_offer_ids = {
                offer.offer_id
                for group in staged.comparison.ranked_groups
                for offer in group.group.offers
            }
            resolved_gaps = set(state.gaps) - set(staged.gaps)
            progress = bool(
                (new_offer_ids & current_group_offer_ids)
                or (current_group_offer_ids - previous_group_offer_ids)
                or resolved_gaps
            )
            if not previous_pool and not incoming:
                progress = False
            usage = AgentRuntimeUsage(
                tool_calls=1,
                retrieval_calls=sum(item.usage.retrieval_calls for item in results),
                model_calls=staged.comparison.model_calls,
            )
            self._ensure_usage_delta(state, usage)
            if not new_offer_ids and previous_pool:
                # 没有新 Offer 时保留上一轮已提交结果，避免一次补查把结果清空。
                state.supplement_no_progress_count = min(2, state.supplement_no_progress_count + 1)
            elif progress:
                state.supplement_no_progress_count = 0
            else:
                state.supplement_no_progress_count = min(2, state.supplement_no_progress_count + 1)
            state.supplement_stage_used = True
            state.supplement_query_fingerprints.extend(item.fingerprint for item in prepared)
            state.query_fingerprints.extend(item.fingerprint for item in prepared)
            state.query_fingerprints = list(dict.fromkeys(state.query_fingerprints))
            state.supplement_query_fingerprints = list(
                dict.fromkeys(state.supplement_query_fingerprints)
            )
            if not new_offer_ids and previous_pool:
                new_records: list[Any] = []
            else:
                new_records = self._commit_staged_evaluation(state, staged)
            state.no_progress_count = 0 if progress else state.no_progress_count + 1
            fallback = bool(merged_result.fallback_used or staged.comparison.fallback_used)
            status = (
                "success"
                if state.ranked_groups
                else "fallback"
                if fallback or previous_pool
                else "no_results"
            )
            return (
                ToolObservation(
                    status=status,
                    result_refs=[group.group.group_id for group in state.ranked_groups][:50],
                    new_evidence_ids=[item.evidence_id for item in new_records][:50],
                    gaps=list(state.gaps),
                    conflicts=list(state.conflicts),
                    fallback_reason=(
                        "supplement_no_progress"
                        if not progress
                        else "retrieval_fallback"
                        if fallback
                        else None
                    ),
                    constraints_version=state.constraints_version,
                    evidence_version=state.evidence_version,
                    usage=usage,
                ),
                None,
                None,
            )
        if isinstance(action, InspectEvidenceAction):
            inspection = self._evidence.inspect(
                state.evidence,
                action.evidence_ids,
                fields=action.fields,
                constraints_version=state.constraints_version,
            )
            if inspection.invalid_ids:
                state.conflicts.extend(
                    [f"invalid_evidence:{item}" for item in inspection.invalid_ids]
                )
            if action.candidate_ids:
                candidates_by_id = {
                    item.offer.offer_id: item
                    for item in (state.recall_pool or state.last_candidates)
                }
                selected: list[RetrievalCandidate] = []
                for candidate_id in [
                    *action.candidate_ids,
                    *[item.offer.offer_id for item in state.last_candidates],
                ]:
                    candidate = candidates_by_id.get(candidate_id)
                    if candidate is not None and candidate.offer.offer_id not in {
                        item.offer.offer_id for item in selected
                    }:
                        selected.append(candidate)
                if selected and constraints is not None:
                    staged = await self._stage_candidate_evaluation(
                        list(state.recall_pool or state.last_candidates),
                        constraints,
                        window_override=selected,
                        query_fingerprints=state.query_fingerprints,
                        stage="inspect",
                    )
                    usage = AgentRuntimeUsage(
                        tool_calls=1,
                        model_calls=staged.comparison.model_calls,
                    )
                    self._ensure_usage_delta(state, usage)
                    new_records = self._commit_staged_evaluation(state, staged)
                    observation = ToolObservation(
                        status="success" if state.ranked_groups else "no_results",
                        result_refs=[group.group.group_id for group in state.ranked_groups][:50],
                        new_evidence_ids=[item.evidence_id for item in new_records][:50],
                        gaps=list(state.gaps),
                        conflicts=list(state.conflicts),
                        constraints_version=state.constraints_version,
                        evidence_version=state.evidence_version,
                        usage=usage,
                    )
                    return observation, None, None
            observation = ToolObservation(
                status="failed" if inspection.invalid_ids else "success",
                result_refs=[item.evidence_id for item in inspection.records],
                gaps=list(state.gaps),
                conflicts=list(state.conflicts),
                constraints_version=state.constraints_version,
                evidence_version=state.evidence_version,
                usage=AgentRuntimeUsage(tool_calls=1),
            )
            return observation, None, None
        if isinstance(action, DelegateResearchAction):
            if self._research is None:
                raise ActionRejectedError("research_decision 未装配")
            ledger = BudgetLedger.start(state.budget, state.usage)
            if not ledger.can_subagent():
                raise BudgetExceededError("subagent 启动次数超限")
            child_budget = ledger.child_budget(
                SubagentBudget(
                    max_decisions=self._settings.subagent_max_decisions,
                    max_tool_calls=self._settings.subagent_max_tool_calls,
                    max_seconds=self._settings.subagent_max_seconds,
                    max_tokens=self._settings.subagent_max_tokens,
                )
            )
            state.usage = state.usage.add(AgentRuntimeUsage(subagent_starts=1))
            parent_action_id = state.actions[-1].action_id if state.actions else "main-action"
            task = SubagentTask(
                task_id=self._subagent_task_id(state, action),
                parent_action_id=parent_action_id,
                role=SubagentRole.RESEARCH,
                objective=action.objective,
                constraints=state.understanding.constraints.model_copy(deep=True)
                if state.understanding.constraints is not None
                else ShoppingConstraints(),
                constraints_version=state.constraints_version,
                evidence_version=state.evidence_version,
                constraints_ref=f"constraints-v{state.constraints_version}",
                disputed_fields=[],
                allowed_evidence_ids=list(state.evidence)[:50],
                allowed_tools=["search_once", "inspect_evidence", "compare_candidates"],
                budget=child_budget,
                deadline_at=(
                    datetime.now(UTC) + timedelta(seconds=child_budget.max_seconds)
                ).isoformat(),
            )
            outcome = await self._research.run(
                task,
                existing_candidates=state.recall_pool or state.last_candidates,
                existing_evidence=state.evidence,
                recognition=state.understanding.recognition,
                image=state.current_request.image,
            )
            self._ensure_usage_delta(state, outcome.result.usage)
            observation = await self._merge_research_result(
                state, outcome.result, outcome.candidates
            )
            state.supplement_stage_used = True
            return observation, None, None
        if isinstance(action, DelegateVerificationAction):
            if self._verification is None:
                raise ActionRejectedError("verification 能力未装配")
            ledger = BudgetLedger.start(state.budget, state.usage)
            if not ledger.can_subagent():
                raise BudgetExceededError("subagent 启动次数超限")
            child_budget = ledger.child_budget(
                SubagentBudget(
                    max_decisions=self._settings.subagent_max_decisions,
                    max_tool_calls=self._settings.subagent_max_tool_calls,
                    max_seconds=self._settings.subagent_max_seconds,
                    max_tokens=self._settings.subagent_max_tokens,
                )
            )
            state.usage = state.usage.add(AgentRuntimeUsage(subagent_starts=1))
            parent_action_id = state.actions[-1].action_id if state.actions else "main-action"
            constraints = state.understanding.constraints
            if constraints is None:
                raise ActionRejectedError("缺少当前约束，不能启动 Verification")
            task = SubagentTask(
                task_id=self._subagent_task_id(state, action),
                parent_action_id=parent_action_id,
                role=SubagentRole.VERIFICATION,
                objective="核验候选的争议字段：" + ",".join(action.disputed_fields),
                constraints=constraints.model_copy(deep=True),
                constraints_version=state.constraints_version,
                evidence_version=state.evidence_version,
                constraints_ref=f"constraints-v{state.constraints_version}",
                allowed_evidence_ids=list(action.evidence_ids or list(state.evidence))[:50],
                disputed_fields=list(action.disputed_fields),
                allowed_tools=["inspect_evidence", "get_offer_details", "compare_candidates"],
                budget=child_budget,
                deadline_at=(
                    datetime.now(UTC) + timedelta(seconds=child_budget.max_seconds)
                ).isoformat(),
            )
            outcome = await self._verification.run(
                task,
                candidate_ids=list(action.candidate_ids),
                existing_candidates=state.recall_pool or state.last_candidates,
                existing_evidence=state.evidence,
            )
            observation = await self._merge_verification_result(
                state, outcome.result, outcome.candidates, action.disputed_fields
            )
            return observation, None, None
        if isinstance(action, AnswerAction):
            response = await self._answer_response(
                state,
                context,
                suppress_side_effects=suppress_side_effects,
                pause_for_hitl=pause_for_hitl,
            )
            if response is not None:
                return None, response, state.active_interrupt
            return None, None, state.active_interrupt
        if isinstance(action, AskUserAction):
            interrupt = self._make_interrupt(
                state,
                InterruptKind.CLARIFICATION,
                "请补充信息后继续比价。",
                {"missing_fields": action.missing_fields, "question_type": action.question_type},
            )
            if pause_for_hitl and self._settings.hitl_enabled:
                state.active_interrupt = interrupt
                return None, None, interrupt
            response = self._clarification_response(state, action.missing_fields)
            return None, response, None
        response = self._base_response(
            state,
            AgentStatus.NO_RESULTS,
            "当前条件下没有符合要求的比价结果。",
        )
        return None, response, None

    async def _stage_candidate_evaluation(
        self,
        pool: list[RetrievalCandidate],
        constraints: ShoppingConstraints,
        *,
        comparison: Any | None = None,
        window_override: list[RetrievalCandidate] | None = None,
        query_fingerprints: list[str] | None = None,
        query_assumptions: list[str] | None = None,
        retrieval_metadata: dict[str, Any] | None = None,
        stage: str,
    ) -> _StagedCandidateEvaluation:
        if window_override is not None:
            by_id: dict[str, RetrievalCandidate] = {}
            for item in window_override:
                by_id.setdefault(item.offer.offer_id, item)
            window = list(by_id.values())[: self._settings.matching_candidate_limit]
        else:
            window = select_candidate_window(
                pool, limit=self._settings.matching_candidate_limit
            ).candidates
        compared = comparison
        if compared is None:
            compared = await self._retrieval.comparison.compare_candidates(window, constraints)
        records = self._evidence.register(compared.ranked_groups)
        assessment = (
            compared.assessment.model_dump(mode="json") if compared.assessment is not None else None
        )
        if assessment is not None:
            unassessed = max(0, len(pool) - len(window))
            assessment.update(
                {
                    "total_hits": len(pool),
                    "unique_offers": len({item.offer.offer_id for item in pool}),
                    "selected_window": len(window),
                    "unassessed": unassessed,
                    "truncated": max(0, len(pool) - len(window)),
                    "query_count": len(query_fingerprints or []),
                    "query_fingerprints": list(query_fingerprints or []),
                    "query_assumptions": list(query_assumptions or []),
                    "stage": stage,
                    **(retrieval_metadata or {}),
                }
            )
            if assessment["truncated"] and "recall_window_truncated" not in assessment["gaps"]:
                assessment["gaps"].append("recall_window_truncated")
        gaps = [] if compared.ranked_groups else ["no_qualified_candidates"]
        if assessment is not None:
            gaps.extend(item for item in assessment["gaps"] if item not in gaps)
        if compared.review_pairs and "same_item_uncertain" not in gaps:
            gaps.append("same_item_uncertain")
        return _StagedCandidateEvaluation(
            recall_pool=list(pool),
            window=window,
            comparison=compared,
            evidence_records=records,
            assessment=assessment,
            gaps=gaps,
            conflicts=[risk for group in compared.ranked_groups for risk in group.group.risks],
            notices=list(compared.notices or []),
        )

    def _commit_staged_evaluation(
        self,
        state: MainRuntimeState,
        staged: _StagedCandidateEvaluation,
    ) -> list[Any]:
        new_records = [
            item for item in staged.evidence_records if item.evidence_id not in state.evidence
        ]
        state.evidence.update({item.evidence_id: item for item in new_records})
        if new_records:
            state.evidence_version += 1
        state.recall_pool = list(staged.recall_pool)
        state.last_candidates = list(staged.window)
        state.ranked_groups = list(staged.comparison.ranked_groups)
        state.retrieval_assessment = staged.assessment
        state.gaps = list(staged.gaps)
        state.conflicts = list(staged.conflicts)[:20]
        if staged.notices:
            state.notices.extend(staged.notices)
        return new_records

    def _subagent_task_id(self, state: MainRuntimeState, action: MainAction) -> str:
        digest = content_hash(
            {
                "session_id": state.session_id,
                "request_id": state.request_id,
                "kind": action.kind.value,
                "objective": getattr(action, "objective", ""),
            }
        )[:24]
        return f"{action.kind.value}:{digest}"

    async def _merge_research_result(
        self,
        state: MainRuntimeState,
        result: SubagentResult,
        candidates: list[Any],
    ) -> ToolObservation:
        """把子结果当作不可信输入：版本、任务和证据引用全部重验。"""
        if result.role is not SubagentRole.RESEARCH:
            raise ActionRejectedError("子结果 role 不匹配")
        if result.parent_action_id != (state.actions[-1].action_id if state.actions else ""):
            raise ActionRejectedError("子结果 parent_action_id 不匹配")
        if result.constraints_version != state.constraints_version:
            raise ActionRejectedError("子结果 constraints_version 已过期")
        if len(set(result.query_fingerprints)) != len(result.query_fingerprints):
            raise ActionRejectedError("子结果包含重复 query fingerprint")
        if set(result.query_fingerprints) & set(state.query_fingerprints):
            raise ActionRejectedError("子结果引用了已执行的 query")
        if any(item.offer.offer_id not in result.candidate_ids for item in candidates):
            raise ActionRejectedError("子结果返回了未声明的 candidate_id")
        merged = {
            item.offer.offer_id: item for item in (state.recall_pool or state.last_candidates)
        }
        merged.update({item.offer.offer_id: item for item in candidates})
        if any(item not in merged for item in result.candidate_ids):
            raise ActionRejectedError("子结果引用了不存在的 candidate_id")
        constraints = state.understanding.constraints
        if constraints is None:
            raise ActionRejectedError("缺少当前约束，不能归并 Research 结果")
        merged_pool = list(merged.values())[: self._settings.retrieval_union_limit]
        window = select_candidate_window(
            merged_pool, limit=self._settings.matching_candidate_limit
        ).candidates
        compared = await self._retrieval.comparison.compare_candidates(window, constraints)
        staged = await self._stage_candidate_evaluation(
            merged_pool,
            constraints,
            comparison=compared,
            query_fingerprints=result.query_fingerprints,
            stage="research",
        )
        available_evidence = set(state.evidence) | {
            item.evidence_id for item in staged.evidence_records
        }
        if any(item not in available_evidence for item in result.evidence_ids):
            raise ActionRejectedError("子结果引用了未注册的 evidence_id")
        usage = result.usage.model_copy(
            update={"model_calls": result.usage.model_calls + compared.model_calls}
        )
        self._ensure_usage_delta(state, usage)
        records = staged.evidence_records
        new_records = [item for item in records if item.evidence_id not in state.evidence]
        state.evidence.update({item.evidence_id: item for item in new_records})
        if new_records:
            state.evidence_version += 1
        state.recall_pool = merged_pool
        state.last_candidates = staged.window
        state.ranked_groups = staged.comparison.ranked_groups
        state.query_fingerprints = list(
            dict.fromkeys([*state.query_fingerprints, *result.query_fingerprints])
        )
        state.supplement_query_fingerprints = list(
            dict.fromkeys([*state.supplement_query_fingerprints, *result.query_fingerprints])
        )
        state.retrieval_assessment = (
            staged.assessment if staged.assessment is not None else state.retrieval_assessment
        )
        state.subagent_results.append(result)
        state.gaps = list(result.unresolved_fields)
        state.gaps.extend(item for item in staged.gaps if item not in state.gaps)
        if not state.gaps and not state.ranked_groups:
            state.gaps = ["no_qualified_candidates"]
        state.conflicts = list(staged.conflicts)[:20]
        if result.status is SubagentStatus.NEEDS_USER_INPUT:
            status = "fallback"
        elif result.status is SubagentStatus.FAILED:
            status = "failed"
        elif not state.ranked_groups:
            status = "no_results"
        else:
            status = "success" if result.status is SubagentStatus.COMPLETE else "fallback"
        return ToolObservation(
            status=status,
            result_refs=[group.group.group_id for group in state.ranked_groups][:50],
            new_evidence_ids=[item.evidence_id for item in new_records][:50],
            gaps=list(state.gaps),
            conflicts=list(state.conflicts),
            fallback_reason=result.end_reason if status == "fallback" else None,
            constraints_version=state.constraints_version,
            evidence_version=state.evidence_version,
            usage=usage,
        )

    async def _merge_verification_result(
        self,
        state: MainRuntimeState,
        result: SubagentResult,
        candidates: list[Any],
        disputed_fields: list[str],
    ) -> ToolObservation:
        if result.role is not SubagentRole.VERIFICATION:
            raise ActionRejectedError("子结果 role 不匹配")
        if result.parent_action_id != (state.actions[-1].action_id if state.actions else ""):
            raise ActionRejectedError("子结果 parent_action_id 不匹配")
        if result.constraints_version != state.constraints_version:
            raise ActionRejectedError("子结果 constraints_version 已过期")
        merged = {
            item.offer.offer_id: item for item in (state.recall_pool or state.last_candidates)
        }
        merged.update({item.offer.offer_id: item for item in candidates})
        if any(item not in merged for item in result.candidate_ids):
            raise ActionRejectedError("核验结果引用了不存在的 candidate_id")
        constraints = state.understanding.constraints
        if constraints is None:
            raise ActionRejectedError("缺少当前约束，不能归并 Verification 结果")
        merged_pool = list(merged.values())[: self._settings.retrieval_union_limit]
        window = select_candidate_window(
            merged_pool, limit=self._settings.matching_candidate_limit
        ).candidates
        if not result.candidate_ids:
            raise ActionRejectedError("核验结果缺少 candidate_id")
        compared = await self._retrieval.comparison.compare_candidates(window, constraints)
        staged = await self._stage_candidate_evaluation(
            merged_pool,
            constraints,
            comparison=compared,
            stage="verification",
        )
        available_evidence = set(state.evidence) | {
            item.evidence_id for item in staged.evidence_records
        }
        if any(item not in available_evidence for item in result.evidence_ids):
            raise ActionRejectedError("核验结果引用了未注册的 evidence_id")
        # recommendation 只由当前 Offer、字段和共享比较结果计算，忽略模型的自由判断。
        from shijiajing_agent.agent_runtime.subagents.verification import VerificationSubagent

        selected = [merged[item] for item in result.candidate_ids]
        selected_compared = await self._retrieval.comparison.compare_candidates(
            selected, constraints
        )
        recommendation = VerificationSubagent.deterministic_recommendation(
            selected, selected_compared.ranked_groups, disputed_fields
        )
        if result.recommendation is not None and result.recommendation != recommendation:
            raise ActionRejectedError("核验模型建议与确定性硬约束判定冲突")
        usage = result.usage.model_copy(
            update={
                "model_calls": (
                    result.usage.model_calls + compared.model_calls + selected_compared.model_calls
                )
            }
        )
        self._ensure_usage_delta(state, usage)
        records = staged.evidence_records
        new_records = [item for item in records if item.evidence_id not in state.evidence]
        state.evidence.update({item.evidence_id: item for item in new_records})
        if new_records:
            state.evidence_version += 1
        state.recall_pool = merged_pool
        state.last_candidates = staged.window
        state.ranked_groups = staged.comparison.ranked_groups
        state.retrieval_assessment = (
            staged.assessment if staged.assessment is not None else state.retrieval_assessment
        )
        state.subagent_results.append(result.model_copy(update={"recommendation": recommendation}))
        state.gaps = (
            []
            if recommendation == "comparable"
            else list(result.unresolved_fields) or [recommendation]
        )
        state.gaps.extend(item for item in staged.gaps if item not in state.gaps)
        state.conflicts = list(staged.conflicts)[:20]
        status = "success" if recommendation == "comparable" else "fallback"
        return ToolObservation(
            status=status,
            result_refs=[group.group.group_id for group in state.ranked_groups][:50],
            new_evidence_ids=[item.evidence_id for item in new_records][:50],
            gaps=list(state.gaps),
            conflicts=list(state.conflicts),
            fallback_reason=None if status == "success" else recommendation,
            constraints_version=state.constraints_version,
            evidence_version=state.evidence_version,
            usage=usage,
        )

    async def _answer_response(
        self,
        state: MainRuntimeState,
        context: AgentExecutionContext,
        *,
        suppress_side_effects: bool,
        pause_for_hitl: bool,
    ) -> AgentResponse | None:
        if not state.ranked_groups:
            if state.last_tool_status == "failed":
                return self._base_response(
                    state, AgentStatus.FAILED, "检索服务不可用，请稍后重试。"
                )
            return self._base_response(
                state, AgentStatus.NO_RESULTS, "当前条件下没有符合要求的比价结果。"
            )
        assert state.understanding.constraints is not None
        answer = await self._answer.render(
            state.ranked_groups,
            state.understanding.constraints,
            state.evidence,
            constraints_version=state.constraints_version,
            notices=state.notices,
        )
        response = self._base_response(state, AgentStatus.SUCCESS, answer.text)
        response = response.model_copy(update={"groups": state.ranked_groups})
        if state.pending_mutations and context.memory_enabled and context.memory_owner_id:
            if suppress_side_effects:
                state.notices.append("只读执行：未提交 Memory 副作用")
            elif not state.memory_authorized:
                if pause_for_hitl and self._settings.hitl_enabled:
                    state.pending_response = response
                    interrupt = self._make_interrupt(
                        state,
                        InterruptKind.MEMORY_CONFIRMATION,
                        "本轮请求包含长期偏好变更，是否保存？",
                        {
                            "mutations": [
                                item.model_dump(mode="json") for item in state.pending_mutations
                            ]
                        },
                    )
                    state.active_interrupt = interrupt
                    return None
                state.notices.append("长期偏好未获授权，本轮未提交")
            else:
                await self._commit_memory(state, context)
        return response.model_copy(update={"notices": list(state.notices)})

    async def _commit_memory(self, state: MainRuntimeState, context: AgentExecutionContext) -> None:
        if not context.memory_owner_id or not state.pending_mutations:
            return
        interrupt_id = str(
            state.context.get("memory_authorization_interrupt_id") or f"auto:{state.turn_id}"
        )
        authorization = str(
            state.context.get("memory_authorization_id")
            or memory_authorization_id(interrupt_id, state.pending_mutations)
        )
        try:
            await self._memory.commit(
                context.memory_owner_id,
                state.pending_mutations,
                interrupt_id=interrupt_id,
                authorization_id=authorization,
            )
            state.pending_mutations = []
            state.notices.append("已按你的明确要求更新长期偏好")
        except Exception:
            state.notices.append("长期偏好保存失败，本轮结果未声明已记住")

    async def _terminal(
        self,
        state: MainRuntimeState,
        context: AgentExecutionContext,
        *,
        suppress_side_effects: bool,
        reason: str,
    ) -> MainAgentRunResult:
        state.notices.append(f"主 Agent 已确定性降级：{reason}")
        if (
            not state.understanding.constraints
            or not state.understanding.constraints.category_id.value
        ):
            response = self._clarification_response(state, ["category_id"])
        elif not state.ranked_groups:
            status, message = self._fallback.response_status(state)
            response = self._base_response(state, status, message)
        else:
            response = await self._answer_response(
                state,
                context,
                suppress_side_effects=suppress_side_effects,
                pause_for_hitl=False,
            )
            if response is None:
                response = state.pending_response or self._base_response(
                    state, AgentStatus.FAILED, "处理失败，请稍后重试。"
                )
        state.final_response = response
        await self._save_session(state)
        await self._save(state, await self._checkpoint_version(state))
        return MainAgentRunResult(state, response)

    async def _apply_resume(
        self,
        state: MainRuntimeState,
        resume: AgentResume,
        context: AgentExecutionContext,
        *,
        suppress_side_effects: bool,
    ) -> AgentResponse | None:
        active = state.active_interrupt
        if active is None:
            return state.final_response
        if resume.interrupt_id != active.interrupt_id:
            raise ValueError("interrupt_id 不匹配")
        if resume.interrupt_id in state.resume_history:
            return state.final_response or state.pending_response
        stage = active.kind
        if stage is InterruptKind.CLARIFICATION:
            from shijiajing_agent.contracts import ClarificationResume

            answer = ClarificationResume.model_validate(resume.value)
            if answer.action == "answer":
                state.current_request = state.current_request.model_copy(
                    update={"text": answer.text, "selected_option_id": None}
                )
            else:
                state.current_request = state.current_request.model_copy(
                    update={"text": answer.option_id, "selected_option_id": answer.option_id}
                )
            await self._prepare(
                state,
                context,
                previous_constraints=state.understanding.constraints,
                previous_recognition=state.understanding.recognition,
                recent_turns=[],
                reset_results=True,
            )
        elif stage is InterruptKind.RECOGNITION_REVIEW:
            answer = RecognitionReviewResume.model_validate(resume.value)
            previous = state.understanding.recognition
            if answer.action == "reject":
                state.understanding = state.understanding.model_copy(update={"recognition": None})
            elif answer.action == "edit" and answer.correction is not None and previous is not None:
                state.current_request = state.current_request.model_copy(
                    update={"correction": answer.correction}
                )
                await self._prepare(
                    state,
                    context,
                    previous_constraints=state.understanding.constraints,
                    previous_recognition=previous,
                    recent_turns=[],
                    reset_results=True,
                )
        elif stage is InterruptKind.SAME_ITEM_REVIEW:
            answer = SameItemReviewResume.model_validate(resume.value)
            if answer.action == "split" and state.last_candidates:
                raw_pairs: Any = active.payload.get("pairs", [])
                pairs: list[Any] = cast(list[Any], raw_pairs) if isinstance(raw_pairs, list) else []
                ids = {
                    str(item)
                    for pair in pairs
                    if isinstance(pair, dict)
                    for item in (
                        cast(dict[str, Any], pair).get("offer_a_id"),
                        cast(dict[str, Any], pair).get("offer_b_id"),
                    )
                    if item
                }
                if state.understanding.constraints is not None:
                    comparison = self._retrieval.comparison
                    compared = await comparison.compare_candidates(
                        state.last_candidates,
                        state.understanding.constraints,
                        split_offer_ids=ids,
                    )
                    state.ranked_groups = compared.ranked_groups
                    state.retrieval_assessment = (
                        compared.assessment.model_dump(mode="json")
                        if compared.assessment is not None
                        else state.retrieval_assessment
                    )
                    records = self._evidence.register(state.ranked_groups)
                    state.evidence.update({item.evidence_id: item for item in records})
                    state.evidence_version += 1
                    state.gaps = []
        elif stage is InterruptKind.MEMORY_CONFIRMATION:
            answer = MemoryConfirmationResume.model_validate(resume.value)
            if answer.action == "approve":
                state.memory_authorized = True
                state.context["memory_authorization_interrupt_id"] = active.interrupt_id
                state.context["memory_authorization_id"] = memory_authorization_id(
                    active.interrupt_id, state.pending_mutations
                )
                await self._commit_memory(state, context)
            else:
                state.pending_mutations = []
                state.notices.append("已取消本轮长期偏好保存")
            if state.pending_response is not None:
                response = state.pending_response.model_copy(
                    update={"notices": list(state.notices)}
                )
                state.pending_response = None
                state.final_response = response
                state.active_interrupt = None
                state.resume_history.append(resume.interrupt_id)
                await self._save_session(state)
                return response
        state.active_interrupt = None
        state.completed_interrupts.append(stage.value)
        state.resume_history.append(resume.interrupt_id)
        return None

    def _base_response(
        self, state: MainRuntimeState, status: AgentStatus, message: str
    ) -> AgentResponse:
        return AgentResponse(
            session_id=state.session_id,
            request_id=state.request_id,
            turn_id=state.turn_id,
            status=status,
            message=message,
            recognition=state.understanding.recognition,
            effective_constraints=state.understanding.constraints,
            groups=list(state.ranked_groups),
            notices=list(state.notices),
            trace_id=state.trace_id,
        )

    def _clarification_response(self, state: MainRuntimeState, missing: list[str]) -> AgentResponse:
        clarification = Clarification(
            question_id=f"q:{state.request_id}",
            question="请补充商品品类后继续比价。",
            reason_code="MISSING_CATEGORY",
            missing_fields=missing,
            turn_id=state.turn_id,
        )
        return self._base_response(
            state, AgentStatus.CLARIFICATION, clarification.question
        ).model_copy(update={"clarification": clarification})

    @staticmethod
    def _interrupt_response(state: MainRuntimeState, interrupt: AgentInterrupt) -> AgentResponse:
        return AgentResponse(
            session_id=state.session_id,
            request_id=state.request_id,
            turn_id=state.turn_id,
            status=AgentStatus.CLARIFICATION,
            message=interrupt.prompt,
            recognition=state.understanding.recognition,
            effective_constraints=state.understanding.constraints,
            groups=list(state.ranked_groups),
            notices=list(state.notices),
            trace_id=state.trace_id,
        )

    def _make_interrupt(
        self,
        state: MainRuntimeState,
        kind: InterruptKind,
        prompt: str,
        payload: dict[str, Any],
    ) -> AgentInterrupt:
        generation = state.interrupt_generation + 1
        digest = hashlib.sha256(
            f"{state.session_id}|{state.request_id}|{state.turn_id}|{kind.value}|{generation}".encode()
        ).hexdigest()
        state.interrupt_generation = generation
        return AgentInterrupt(
            interrupt_id=digest,
            session_id=state.session_id,
            request_id=state.request_id,
            turn_id=state.turn_id,
            trace_id=state.trace_id,
            kind=kind,
            prompt=prompt,
            payload={
                "engine_version": self.engine_version,
                "constraints_version": state.constraints_version,
                "evidence_version": state.evidence_version,
                **payload,
            },
        )

    def _action_id(self, state: MainRuntimeState, action: MainAction, fingerprint: str) -> str:
        return hashlib.sha256(
            (
                f"{state.session_id}|{state.request_id}|{len(state.actions) + 1}|"
                f"{action.kind.value}|{fingerprint}"
            ).encode()
        ).hexdigest()

    def _ensure_within_budget(self, state: MainRuntimeState) -> None:
        ledger = BudgetLedger.start(state.budget, state.usage)
        if state.usage.decisions > state.budget.max_decisions:
            raise BudgetExceededError("主 Agent 决策次数超限")
        if state.usage.model_calls > state.budget.max_model_calls:
            raise BudgetExceededError("生成模型调用次数超限")
        if state.usage.input_tokens + state.usage.output_tokens > state.budget.max_tokens:
            raise BudgetExceededError("模型 token 预算超限")
        if ledger.expired():
            raise BudgetExceededError("主 Agent 执行时限超限")

    @staticmethod
    def _ensure_usage_delta(state: MainRuntimeState, delta: AgentRuntimeUsage) -> None:
        next_usage = state.usage.add(delta)
        if next_usage.decisions > state.budget.max_decisions:
            raise BudgetExceededError("主 Agent 决策次数超限")
        if next_usage.tool_calls > state.budget.max_tool_calls:
            raise BudgetExceededError("工具派发次数超限")
        if next_usage.retrieval_calls > state.budget.max_retrieval_calls:
            raise BudgetExceededError("真实检索次数超限")
        if next_usage.model_calls > state.budget.max_model_calls:
            raise BudgetExceededError("生成模型调用次数超限")
        if next_usage.input_tokens + next_usage.output_tokens > state.budget.max_tokens:
            raise BudgetExceededError("模型 token 预算超限")

    def _add_usage(self, state: MainRuntimeState, usage: AgentRuntimeUsage) -> None:
        self._ensure_usage_delta(state, usage)
        next_usage = state.usage.add(usage)
        state.usage = next_usage

    async def _save(self, state: MainRuntimeState, version: int | None) -> None:
        self._local_states[(state.session_id, state.request_id)] = state.model_copy(deep=True)
        if self._checkpoint is not None:
            await self._checkpoint.save_request(state, version)

    async def _checkpoint_version(self, state: MainRuntimeState) -> int | None:
        if self._checkpoint is None:
            return None
        loaded = await self._checkpoint.load_request(state.session_id, state.request_id)
        return loaded[1] if loaded is not None else None

    async def _save_session(self, state: MainRuntimeState) -> None:
        previous = await self._load_session(state.session_id)
        summary = self._turn_summary(state)
        recent_turns = [*(previous.recent_turns if previous is not None else []), summary]
        recent_turns = self._trim_recent_turns(recent_turns)
        snapshot = RuntimeSessionSnapshot(
            session_id=state.session_id,
            engine_version=self.engine_version,
            version=previous.version + 1 if previous is not None else 1,
            subject_id=state.understanding.constraints.category_id.value
            if state.understanding.constraints is not None
            else None,
            constraints=state.understanding.constraints,
            recognition=state.understanding.recognition,
            recent_turns=recent_turns,
        )
        self._local_sessions[state.session_id] = snapshot
        if self._checkpoint is not None:
            await self._checkpoint.save_session(snapshot)

    async def _load_session(self, session_id: str) -> RuntimeSessionSnapshot | None:
        if self._checkpoint is not None:
            value = await self._checkpoint.load_session(session_id)
            if value is not None:
                return value
        return self._local_sessions.get(session_id)

    async def _load_active(self, session_id: str) -> tuple[str, MainRuntimeState, int] | None:
        if self._checkpoint is not None:
            return await self._checkpoint.load_active(session_id)
        for (saved_session, _), state in self._local_states.items():
            if saved_session == session_id and state.active_interrupt is not None:
                return ("local", state.model_copy(deep=True), 0)
        return None

    @staticmethod
    def _recent_turns(snapshot: RuntimeSessionSnapshot | None) -> list[ConversationTurnSummary]:
        if snapshot is None:
            return []
        return [ConversationTurnSummary.model_validate(item) for item in snapshot.recent_turns]

    def _turn_summary(self, state: MainRuntimeState) -> dict[str, Any]:
        patch = state.understanding.intent_patch
        delta: dict[str, Any] = {}
        if patch is not None:
            # 会话摘要只保留“哪些字段本轮触及”，不复制用户全文或记忆值。
            for key, value in patch.model_dump(mode="json").items():
                if value is not None and key != "memory_directives":
                    delta[key] = True
        response = state.final_response
        if response is None:
            reason = None
        elif response.status is AgentStatus.SUCCESS:
            reason = CompletionReason.SUCCESS
        elif response.status is AgentStatus.CLARIFICATION:
            reason = CompletionReason.CLARIFICATION
        elif response.status is AgentStatus.NO_RESULTS:
            reason = CompletionReason.NO_RESULTS
        else:
            reason = CompletionReason.FAILED
        summary = ConversationTurnSummary(
            request_id=state.request_id,
            turn_id=state.turn_id,
            subject_id=(
                state.understanding.constraints.category_id.value
                if state.understanding.constraints is not None
                else None
            ),
            category_id=(
                state.understanding.constraints.category_id.value
                if state.understanding.constraints is not None
                else None
            ),
            constraint_delta=delta,
            memory_effects=[
                {"operation": item.operation.value, "scope_key": item.scope_key}
                for item in state.pending_mutations
            ],
            intent_patch=patch,
            completion_reason=reason,
            selected_group_ids=[item.group.group_id for item in state.ranked_groups[:3]],
            created_at=now_iso(),
        )
        return summary.model_dump(mode="json")

    def _trim_recent_turns(self, turns: list[dict[str, Any]]) -> list[dict[str, Any]]:
        # 先按数量裁剪，再按配置的字节上限从最旧摘要开始丢弃。
        result = turns[-self._settings.recent_turns_limit :]
        while (
            result
            and len(json.dumps(result, ensure_ascii=False).encode("utf-8"))
            > self._settings.recent_turns_max_bytes
        ):
            result = result[1:]
        return result


__all__ = ["MainAgentRunResult", "MainAgentRuntime"]
