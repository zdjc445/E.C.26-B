"""复杂检索 subagent：受限观察、有限动作和父预算共享。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from time import monotonic
from typing import Any

from shijiajing_agent.agent_runtime.budget import BudgetExceededError
from shijiajing_agent.agent_runtime.contracts import (
    AgentRuntimeUsage,
    SubagentActionKind,
    SubagentCompareCandidatesAction,
    SubagentDecisionResult,
    SubagentFinishAction,
    SubagentInspectEvidenceAction,
    SubagentNeedsUserInputAction,
    SubagentObservation,
    SubagentResult,
    SubagentRole,
    SubagentSearchAction,
    SubagentStatus,
    SubagentTask,
    VerifiedFact,
)
from shijiajing_agent.contracts import (
    ImageRef,
    RankedGroup,
    RecognitionResult,
    RetrievalCandidate,
)
from shijiajing_agent.ports.agent_decision import SubagentDecisionPort
from shijiajing_agent.services.evidence import EvidenceService
from shijiajing_agent.services.retrieval import RetrievalService


@dataclass(frozen=True)
class ResearchRunOutcome:
    result: SubagentResult
    candidates: list[RetrievalCandidate]
    ranked_groups: list[RankedGroup]


class ResearchSubagent:
    """只补齐检索缺口，不回答用户，也不写主状态或长期记忆。"""

    def __init__(
        self,
        decision: SubagentDecisionPort,
        retrieval: RetrievalService,
        evidence: EvidenceService,
        max_queries: int = 3,
    ) -> None:
        self._decision = decision
        self._retrieval = retrieval
        self._evidence = evidence
        self._max_queries = max(1, max_queries)

    async def run(
        self,
        task: SubagentTask,
        *,
        existing_candidates: list[RetrievalCandidate],
        existing_evidence: dict[str, Any],
        recognition: RecognitionResult | None = None,
        image: ImageRef | None = None,
    ) -> ResearchRunOutcome:
        started = monotonic()
        candidates_by_id = {item.offer.offer_id: item for item in existing_candidates}
        evidence = {
            evidence_id: existing_evidence[evidence_id]
            for evidence_id in task.allowed_evidence_ids
            if evidence_id in existing_evidence
        }
        queries: list[str] = []
        query_fingerprints: list[str] = []
        gaps = ["research_not_started"]
        conflicts: list[str] = []
        ranked_groups: list[RankedGroup] = []
        usage = AgentRuntimeUsage()
        no_progress = 0
        invalid_actions = 0
        end_status = SubagentStatus.PARTIAL
        end_reason = "subagent_stopped"

        allowed = self._allowed_actions(task)
        while True:
            if self._expired(started, task.budget.max_seconds):
                end_reason = "deadline_exceeded"
                break
            if usage.decisions >= task.budget.max_decisions:
                end_reason = "decision_budget_exhausted"
                break
            observation = self._observation(
                task,
                candidates_by_id,
                evidence,
                queries,
                gaps,
                conflicts,
                usage,
                allowed,
                started,
            )
            try:
                remaining = self._remaining(started, task.budget.max_seconds)
                async with asyncio.timeout(remaining):
                    decision = await self._decision.decide(observation, allowed)
                decision = self._normalise_decision(decision, allowed)
                usage = usage.add(
                    decision.usage.model_copy(
                        update={"decisions": max(1, decision.usage.decisions)}
                    )
                )
                self._ensure_budget(usage, task)
            except (ValueError, TypeError) as exc:
                invalid_actions += 1
                conflicts = [f"invalid_action:{str(exc)[:80]}"]
                if invalid_actions >= 2:
                    end_reason = "invalid_action_limit"
                    end_status = SubagentStatus.FAILED
                    break
                continue
            except (TimeoutError, BudgetExceededError):
                end_reason = "budget_exhausted"
                break
            except Exception:
                end_reason = "decision_failed"
                end_status = SubagentStatus.FAILED
                break

            invalid_actions = 0
            action = decision.action
            try:
                if isinstance(action, SubagentSearchAction):
                    query = (action.query_text or task.objective).strip()
                    if query in queries:
                        no_progress += 1
                        gaps = ["duplicate_query"]
                    elif len(queries) >= self._max_queries:
                        no_progress += 1
                        gaps = ["supplement_query_limit"]
                        end_reason = "supplement_query_limit"
                        break
                    else:
                        queries.append(query)
                        search = await self._search(
                            started,
                            task,
                            query,
                            action.soft_terms,
                            recognition,
                            image,
                        )
                        usage = usage.add(search.usage)
                        if search.plan is not None:
                            query_fingerprints.extend(
                                item.fingerprint
                                for item in ([search.plan.original_query, *search.plan.variants])
                                if item.fingerprint not in query_fingerprints
                            )
                        before = set(candidates_by_id)
                        candidates_by_id.update(
                            {item.offer.offer_id: item for item in search.candidates}
                        )
                        compared = await self._retrieval.comparison.compare_candidates(
                            list(candidates_by_id.values()), task.constraints
                        )
                        usage = usage.add(
                            AgentRuntimeUsage(
                                model_calls=compared.model_calls,
                                tool_calls=1,
                            )
                        )
                        ranked_groups = compared.ranked_groups
                        before_evidence = set(evidence)
                        for record in self._evidence.register(ranked_groups):
                            evidence[record.evidence_id] = record
                        added = set(candidates_by_id) - before
                        added_evidence = set(evidence) - before_evidence
                        no_progress = 0 if added or added_evidence else no_progress + 1
                        gaps = [] if ranked_groups else ["no_qualified_candidates"]
                        conflicts = [risk for group in ranked_groups for risk in group.group.risks]
                    if no_progress >= 2:
                        end_reason = "no_progress"
                        break
                elif isinstance(action, SubagentInspectEvidenceAction):
                    inspection = self._evidence.inspect(
                        evidence,
                        action.evidence_ids,
                        fields=action.fields,
                        constraints_version=task.constraints_version,
                    )
                    usage = usage.add(AgentRuntimeUsage(tool_calls=1))
                    if inspection.invalid_ids:
                        conflicts = [f"invalid_evidence:{item}" for item in inspection.invalid_ids]
                        no_progress += 1
                    else:
                        conflicts = []
                        gaps = [] if inspection.records else ["evidence_empty"]
                        no_progress = 0 if inspection.records else no_progress + 1
                elif isinstance(action, SubagentCompareCandidatesAction):
                    selected = [
                        candidates_by_id[item]
                        for item in action.candidate_ids
                        if item in candidates_by_id
                    ]
                    if len(selected) != len(set(action.candidate_ids)) or not selected:
                        raise ValueError("compare_candidates 引用了未知 candidate_id")
                    compared = await self._retrieval.comparison.compare_candidates(
                        selected, task.constraints
                    )
                    usage = usage.add(
                        AgentRuntimeUsage(tool_calls=1, model_calls=compared.model_calls)
                    )
                    ranked_groups = compared.ranked_groups
                    for record in self._evidence.register(ranked_groups):
                        evidence[record.evidence_id] = record
                    gaps = [] if ranked_groups else ["no_qualified_candidates"]
                    conflicts = [risk for group in ranked_groups for risk in group.group.risks]
                    no_progress = 0
                elif isinstance(action, SubagentFinishAction):
                    end_status = SubagentStatus(action.status)
                    end_reason = action.end_reason
                    break
                elif isinstance(action, SubagentNeedsUserInputAction):
                    gaps = list(action.unresolved_fields)
                    end_status = SubagentStatus.NEEDS_USER_INPUT
                    end_reason = action.end_reason
                    break
                else:
                    raise ValueError(f"research 不允许动作 {action.kind.value}")
                self._ensure_budget(usage, task)
            except TimeoutError:
                end_reason = "deadline_exceeded"
                break
            except BudgetExceededError:
                end_reason = "budget_exhausted"
                break
            except Exception as exc:
                conflicts = [f"tool_failed:{str(exc)[:80]}"]
                end_reason = "tool_failed"
                end_status = SubagentStatus.FAILED
                break

        candidate_ids = list(candidates_by_id)
        evidence_ids = sorted(
            evidence_id
            for evidence_id, record in evidence.items()
            if record.candidate_id in {group.group.group_id for group in ranked_groups}
        )
        facts = self._facts(evidence)
        result = SubagentResult(
            task_id=task.task_id,
            parent_action_id=task.parent_action_id,
            role=SubagentRole.RESEARCH,
            constraints_version=task.constraints_version,
            evidence_version=task.evidence_version,
            status=end_status,
            candidate_ids=candidate_ids,
            queries=queries,
            query_fingerprints=query_fingerprints,
            facts=facts,
            evidence_ids=evidence_ids,
            unresolved_fields=gaps,
            end_reason=end_reason,
            usage=usage.model_copy(update={"elapsed_ms": (monotonic() - started) * 1000}),
        )
        return ResearchRunOutcome(result, list(candidates_by_id.values()), ranked_groups)

    async def _search(
        self,
        started: float,
        task: SubagentTask,
        query: str,
        soft_terms: list[str],
        recognition: RecognitionResult | None,
        image: ImageRef | None,
    ) -> Any:
        remaining = self._remaining(started, task.budget.max_seconds)
        async with asyncio.timeout(remaining):
            return await self._retrieval.search_once(
                query,
                task.constraints,
                recognition=recognition,
                image=image,
                soft_terms=soft_terms,
                constraints_version=task.constraints_version,
                max_queries=1,
            )

    @staticmethod
    def _normalise_decision(
        decision: SubagentDecisionResult,
        allowed: tuple[SubagentActionKind, ...],
    ) -> SubagentDecisionResult:
        if decision.action.kind not in allowed:
            raise ValueError(f"未授权子动作: {decision.action.kind.value}")
        return decision

    @staticmethod
    def _allowed_actions(task: SubagentTask) -> tuple[SubagentActionKind, ...]:
        actions: list[SubagentActionKind] = []
        if "search_once" in task.allowed_tools:
            actions.append(SubagentActionKind.SEARCH_ONCE)
        if "inspect_evidence" in task.allowed_tools:
            actions.append(SubagentActionKind.INSPECT_EVIDENCE)
        if "compare_candidates" in task.allowed_tools:
            actions.append(SubagentActionKind.COMPARE_CANDIDATES)
        actions.extend((SubagentActionKind.FINISH, SubagentActionKind.NEEDS_USER_INPUT))
        return tuple(actions)

    @staticmethod
    def _observation(
        task: SubagentTask,
        candidates: dict[str, RetrievalCandidate],
        evidence: dict[str, Any],
        queries: list[str],
        gaps: list[str],
        conflicts: list[str],
        usage: AgentRuntimeUsage,
        allowed: tuple[SubagentActionKind, ...],
        started: float,
    ) -> SubagentObservation:
        return SubagentObservation(
            task_id=task.task_id,
            role=task.role,
            objective=task.objective,
            constraints=task.constraints,
            constraints_version=task.constraints_version,
            evidence_version=task.evidence_version,
            focus_fields=list(task.disputed_fields),
            candidate_summary=[
                {
                    "candidate_id": item.offer.offer_id,
                    "title": item.offer.title[:160],
                    "platform": item.offer.platform,
                    "price": item.offer.price,
                    "model": item.offer.model,
                }
                for item in list(candidates.values())[:20]
            ],
            evidence_ids=list(evidence)[:50],
            queries=queries[-10:],
            gaps=gaps[:20],
            conflicts=conflicts[:20],
            available_actions=list(allowed),
            usage=usage,
            remaining_budget=task.budget.model_copy(
                update={
                    "max_decisions": max(1, task.budget.max_decisions - usage.decisions),
                    "max_tool_calls": max(1, task.budget.max_tool_calls - usage.tool_calls),
                    "max_tokens": max(
                        1,
                        task.budget.max_tokens - usage.input_tokens - usage.output_tokens,
                    ),
                    "max_seconds": max(0.001, task.budget.max_seconds - (monotonic() - started)),
                }
            ),
        )

    @staticmethod
    def _facts(evidence: dict[str, Any]) -> list[VerifiedFact]:
        facts: list[VerifiedFact] = []
        for record in evidence.values():
            for field, value in record.fields.items():
                if value is not None:
                    facts.append(
                        VerifiedFact(
                            candidate_id=record.candidate_id,
                            field=field,
                            value=value,
                            evidence_ids=[record.evidence_id],
                        )
                    )
        return facts[:100]

    @staticmethod
    def _ensure_budget(usage: AgentRuntimeUsage, task: SubagentTask) -> None:
        if usage.decisions > task.budget.max_decisions:
            raise BudgetExceededError("subagent 决策次数超限")
        if usage.tool_calls > task.budget.max_tool_calls:
            raise BudgetExceededError("subagent 工具调用次数超限")
        if usage.input_tokens + usage.output_tokens > task.budget.max_tokens:
            raise BudgetExceededError("subagent token 预算超限")

    @staticmethod
    def _expired(started: float, limit: float) -> bool:
        return monotonic() - started >= limit

    @staticmethod
    def _remaining(started: float, limit: float) -> float:
        remaining = limit - (monotonic() - started)
        if remaining <= 0:
            raise TimeoutError
        return remaining


__all__ = ["ResearchRunOutcome", "ResearchSubagent"]
