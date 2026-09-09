"""专项核验 subagent：详情证据可选，结论由确定性比较服务验收。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from time import monotonic
from typing import Any, Literal

from shijiajing_agent.agent_runtime.budget import BudgetExceededError
from shijiajing_agent.agent_runtime.contracts import (
    AgentRuntimeUsage,
    SubagentActionKind,
    SubagentCompareCandidatesAction,
    SubagentDecisionResult,
    SubagentFinishAction,
    SubagentGetOfferDetailsAction,
    SubagentInspectEvidenceAction,
    SubagentNeedsUserInputAction,
    SubagentObservation,
    SubagentResult,
    SubagentRole,
    SubagentStatus,
    SubagentTask,
    VerifiedFact,
)
from shijiajing_agent.contracts import Offer, RankedGroup, RetrievalCandidate
from shijiajing_agent.ports.agent_decision import OfferDetailPort, SubagentDecisionPort
from shijiajing_agent.services.evidence import EvidenceService
from shijiajing_agent.services.retrieval import RetrievalService


@dataclass(frozen=True)
class VerificationRunOutcome:
    result: SubagentResult
    candidates: list[RetrievalCandidate]
    ranked_groups: list[RankedGroup]


class VerificationSubagent:
    """只读取当前候选的证据/详情，不搜索、不记忆、不直接回答用户。"""

    def __init__(
        self,
        decision: SubagentDecisionPort,
        details: OfferDetailPort,
        retrieval: RetrievalService,
        evidence: EvidenceService,
    ) -> None:
        self._decision = decision
        self._details = details
        self._retrieval = retrieval
        self._evidence = evidence

    async def run(
        self,
        task: SubagentTask,
        *,
        candidate_ids: list[str],
        existing_candidates: list[RetrievalCandidate],
        existing_evidence: dict[str, Any],
    ) -> VerificationRunOutcome:
        started = monotonic()
        candidates_by_id = {
            item.offer.offer_id: item
            for item in existing_candidates
            if item.offer.offer_id in candidate_ids
        }
        evidence = {
            evidence_id: existing_evidence[evidence_id]
            for evidence_id in task.allowed_evidence_ids
            if evidence_id in existing_evidence
        }
        queries: list[str] = []
        gaps = ["verification_not_started"]
        conflicts: list[str] = []
        ranked_groups: list[RankedGroup] = []
        recommendation: str | None = None
        usage = AgentRuntimeUsage()
        invalid_actions = 0
        no_progress = 0
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
                async with asyncio.timeout(self._remaining(started, task.budget.max_seconds)):
                    decision = await self._decision.decide(observation, allowed)
                decision = self._validate_decision(decision, allowed)
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
                if isinstance(action, SubagentGetOfferDetailsAction):
                    selected_ids = list(dict.fromkeys(action.candidate_ids))
                    if any(item not in candidates_by_id for item in selected_ids):
                        raise ValueError("get_offer_details 引用了未知 candidate_id")
                    if any(
                        item in queries
                        for item in (
                            f"details:{candidate}:{','.join(action.fields)}"
                            for candidate in selected_ids
                        )
                    ):
                        no_progress += 1
                    else:
                        for candidate_id in selected_ids:
                            queries.append(f"details:{candidate_id}:{','.join(action.fields)}")
                        async with asyncio.timeout(
                            self._remaining(started, task.budget.max_seconds)
                        ):
                            offers = await self._details.get_details(selected_ids, action.fields)
                        usage = usage.add(AgentRuntimeUsage(tool_calls=1))
                        returned = {offer.offer_id: offer for offer in offers}
                        if set(returned) - set(selected_ids):
                            raise ValueError("详情端口返回了未请求的 candidate_id")
                        before = {
                            candidate_id: candidates_by_id[candidate_id].offer
                            for candidate_id in selected_ids
                        }
                        for candidate_id, offer in returned.items():
                            candidates_by_id[candidate_id] = self._replace_offer(
                                candidates_by_id[candidate_id], offer
                            )
                        compared = await self._retrieval.comparison.compare_candidates(
                            list(candidates_by_id.values()), task.constraints
                        )
                        usage = usage.add(
                            AgentRuntimeUsage(
                                tool_calls=1,
                                model_calls=compared.model_calls,
                            )
                        )
                        ranked_groups = compared.ranked_groups
                        before_evidence = set(evidence)
                        for record in self._evidence.register(ranked_groups):
                            evidence[record.evidence_id] = record
                        recommendation = self.deterministic_recommendation(
                            list(candidates_by_id.values()),
                            ranked_groups,
                            action.fields,
                        )
                        changed = any(
                            before[candidate_id] != candidates_by_id[candidate_id].offer
                            for candidate_id in before
                        )
                        no_progress = (
                            0 if changed or set(evidence) - before_evidence else no_progress + 1
                        )
                        gaps = (
                            []
                            if recommendation == "comparable"
                            else list(task.disputed_fields)
                            if recommendation == "insufficient_evidence"
                            else [recommendation or "insufficient_evidence"]
                        )
                        conflicts = []
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
                        gaps = [] if inspection.records else ["insufficient_evidence"]
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
                    recommendation = self.deterministic_recommendation(
                        selected, ranked_groups, task.disputed_fields
                    )
                    gaps = [] if recommendation else ["insufficient_evidence"]
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
                    raise ValueError(f"verification 不允许动作 {action.kind.value}")
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

        result_evidence_ids = sorted(
            evidence_id
            for evidence_id, record in evidence.items()
            if record.candidate_id in {group.group.group_id for group in ranked_groups}
        )
        result = SubagentResult(
            task_id=task.task_id,
            parent_action_id=task.parent_action_id,
            role=SubagentRole.VERIFICATION,
            constraints_version=task.constraints_version,
            evidence_version=task.evidence_version,
            status=end_status,
            candidate_ids=list(candidates_by_id),
            queries=queries,
            facts=self._facts(evidence),
            evidence_ids=result_evidence_ids,
            unresolved_fields=gaps,
            recommendation=recommendation,
            end_reason=end_reason,
            usage=usage.model_copy(update={"elapsed_ms": (monotonic() - started) * 1000}),
        )
        return VerificationRunOutcome(result, list(candidates_by_id.values()), ranked_groups)

    @staticmethod
    def _replace_offer(candidate: RetrievalCandidate, offer: Offer) -> RetrievalCandidate:
        return candidate.model_copy(update={"offer": offer})

    @staticmethod
    def deterministic_recommendation(
        candidates: list[RetrievalCandidate],
        groups: list[RankedGroup],
        fields: list[str],
    ) -> Literal["comparable", "not_comparable", "insufficient_evidence"]:
        if len(candidates) < 2:
            return "insufficient_evidence"
        values: dict[str, set[str]] = {field: set() for field in fields}
        missing: set[str] = set()
        for candidate in candidates:
            offer = candidate.offer
            for field in fields:
                value = VerificationSubagent._offer_field(offer, field)
                if value in (None, ""):
                    missing.add(field)
                else:
                    values[field].add(str(value))
        if any(len(items) > 1 for items in values.values()):
            return "not_comparable"
        if missing or not groups:
            return "insufficient_evidence"
        if len(groups) != 1 or groups[0].group.offer_count < len(candidates):
            return "not_comparable"
        if groups[0].group.missing_sku_attributes:
            return "insufficient_evidence"
        return "comparable"

    @staticmethod
    def _offer_field(offer: Offer, field: str) -> Any:
        if hasattr(offer, field):
            return getattr(offer, field)
        for prefix in ("identity_attributes", "variant_attributes", "descriptive_attributes"):
            values = getattr(offer, prefix)
            if field.startswith(prefix + "."):
                return values.get(field.removeprefix(prefix + "."))
            if field in values:
                return values[field]
        return None

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
    def _allowed_actions(task: SubagentTask) -> tuple[SubagentActionKind, ...]:
        actions: list[SubagentActionKind] = []
        if "inspect_evidence" in task.allowed_tools:
            actions.append(SubagentActionKind.INSPECT_EVIDENCE)
        if "get_offer_details" in task.allowed_tools:
            actions.append(SubagentActionKind.GET_OFFER_DETAILS)
        if "compare_candidates" in task.allowed_tools:
            actions.append(SubagentActionKind.COMPARE_CANDIDATES)
        actions.extend((SubagentActionKind.FINISH, SubagentActionKind.NEEDS_USER_INPUT))
        return tuple(actions)

    @staticmethod
    def _validate_decision(
        decision: SubagentDecisionResult,
        allowed: tuple[SubagentActionKind, ...],
    ) -> SubagentDecisionResult:
        if decision.action.kind not in allowed:
            raise ValueError(f"未授权子动作: {decision.action.kind.value}")
        return decision

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


__all__ = ["VerificationRunOutcome", "VerificationSubagent"]
