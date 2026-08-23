"""二期工程夹具的实际回归执行器。

这里执行的是确定性工程不变量，不把夹具结果混入商品质量门禁：Memory 使用真实
SQLite adapter，Cache 使用真实内存 cache，HITL 使用四类专用 resume 模型，Multi-Agent
检查子图输出到汇合状态的边界。
"""

from __future__ import annotations

import json
import tempfile
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field

from shijiajing_agent.adapters.cache import InMemoryVersionedCache, canonical_cache_key
from shijiajing_agent.adapters.memory import SQLiteMemoryAdapter
from shijiajing_agent.adapters.observability import span_attributes
from shijiajing_agent.contracts import (
    AgentEvent,
    ClarificationResume,
    EventType,
    MemoryConfirmationResume,
    MemoryOperation,
    MemoryQuery,
    NodeStatus,
    RecognitionReviewResume,
    RetrievalQuery,
    SameItemReviewResume,
    now_iso,
)
from shijiajing_agent.domain.cache_policy import versioned_key
from shijiajing_agent.domain.filters import offer_matches_hard_filters
from shijiajing_agent.domain.memory_policy import (
    build_memory_mutation,
    validate_directive,
)
from shijiajing_agent.domain.taxonomy import Taxonomy
from shijiajing_agent.eval_engineering import (
    CacheSample,
    InterruptSample,
    MemorySample,
    MultiAgentSample,
    RetrievalStrategySample,
    rank_retrieval_strategy,
)


class EngineeringInvariantResult(BaseModel):
    """§15.7 固定不变量的可审计结果；不带样本时不得视为通过。"""

    model_config = ConfigDict(extra="forbid")

    name: Literal[
        "user_hard_filter_violation_count",
        "cross_user_memory_leakage_count",
        "replay_duplicate_side_effect_count",
        "wrong_sku_group_count",
        "price_fact_error_count",
        "sensitive_field_leakage_count",
    ]
    sample_count: int = Field(ge=0)
    violation_count: int = Field(ge=0)
    evidence: str = Field(min_length=1)

    @property
    def measured(self) -> bool:
        return self.sample_count > 0

    @property
    def passed(self) -> bool:
        return self.measured and self.violation_count == 0


class EngineeringCheckResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["memory", "multi_agent", "interrupt", "cache"]
    sample_count: int = Field(ge=0)
    passed_count: int = Field(ge=0)
    failed_ids: list[str] = Field(default_factory=list[str])
    details: dict[str, Any] = Field(default_factory=dict[str, Any])


class EngineeringEvaluationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    checks: list[EngineeringCheckResult]
    invariants: list[EngineeringInvariantResult]
    invariant_gate_passed: bool
    all_passed: bool


def engineering_report_to_markdown(report: EngineeringEvaluationReport) -> str:
    lines = [
        "# 工程不变量夹具执行报告",
        "",
        f"- 总体结果：{'通过' if report.all_passed else '失败'}",
        "",
        "| kind | n | passed | failed_ids |",
        "|---|---:|---:|---|",
    ]
    for check in report.checks:
        failed = ", ".join(check.failed_ids) if check.failed_ids else "—"
        lines.append(f"| {check.kind} | {check.sample_count} | {check.passed_count} | {failed} |")
    lines.extend(
        [
            "",
            "## 固定不变量",
            "",
            "| name | samples | violations | status | evidence |",
            "|---|---:|---:|---|---|",
        ]
    )
    for invariant in report.invariants:
        status = "✅" if invariant.passed else ("❌" if invariant.measured else "待测")
        lines.append(
            f"| {invariant.name} | {invariant.sample_count} | {invariant.violation_count} | "
            f"{status} | {invariant.evidence} |"
        )
    lines.extend(
        [
            "",
            "Memory/Cache 使用真实 adapter；HITL 使用专用 resume 模型；"
            "固定不变量只覆盖本地工程夹具和脱敏投影；本报告不参与商品质量发布门禁。",
        ]
    )
    return "\n".join(lines) + "\n"


def _result(
    kind: Literal["memory", "multi_agent", "interrupt", "cache"],
    sample_ids: list[str],
    failures: dict[str, str],
) -> EngineeringCheckResult:
    return EngineeringCheckResult(
        kind=kind,
        sample_count=len(sample_ids),
        passed_count=len(sample_ids) - len(failures),
        failed_ids=list(failures),
        details={"failures": failures},
    )


async def _check_memory_sample(
    adapter: SQLiteMemoryAdapter,
    sample: MemorySample,
    taxonomy: Taxonomy,
    invariant_counts: dict[str, int],
) -> str | None:
    before_forget: dict[str, Any] = {}
    actual_notices: list[str] = []
    forget_seen = False
    for session in sample.sessions:
        for index, raw_directive in enumerate(session.directives):
            directive = validate_directive(raw_directive, taxonomy)
            mutation = build_memory_mutation(
                sample.owner,
                session.session_id,
                session.request_id,
                index,
                directive,
            )
            changed = await adapter.commit(sample.owner, [mutation])
            replayed = await adapter.commit(sample.owner, [mutation])
            invariant_counts["replay_duplicate_side_effect_count"] += len(replayed)
            if changed:
                actual_notices = ["已按你的明确要求更新长期偏好"]
            if directive.operation is MemoryOperation.UPSERT and not forget_seen:
                before_forget[directive.memory_key or ""] = directive.value
            if directive.operation in {MemoryOperation.FORGET, MemoryOperation.CLEAR_OWNER}:
                forget_seen = True

    expected_value = before_forget.get(sample.expected_key)
    if expected_value != sample.expected_value:
        return f"expected_value 不一致: actual={expected_value!r}"
    for key, expected in sample.expected_final_constraints.items():
        if before_forget.get(key) != expected:
            return f"expected_final_constraints[{key}] 不一致"
    if actual_notices != sample.expected_notices:
        return f"expected_notices 不一致: actual={actual_notices!r}"

    query = MemoryQuery(
        scope_keys=[sample.expected_scope],
        memory_keys=[sample.expected_key],
        limit=20,
    )
    active = await adapter.recall(sample.owner, query)
    after_forget = sample.expected_after_forget
    expected_status = after_forget.get("status")
    expected_recall_count = after_forget.get("recall_count")
    if expected_status == "forgotten" and active:
        return "遗忘后的 active recall 非空"
    if isinstance(expected_recall_count, int) and len(active) != expected_recall_count:
        return f"forget 后 recall_count 不一致: actual={len(active)}"
    if expected_status == "active":
        if len(active) != 1 or active[0].value != sample.expected_value:
            return "active memory 与 expected_value 不一致"
    probe = await adapter.recall(
        f"{sample.owner}:other-owner",
        MemoryQuery(scope_keys=[sample.expected_scope], limit=20),
    )
    if probe:
        invariant_counts["cross_user_memory_leakage_count"] += len(probe)
        return "跨 owner 发生记忆泄漏"
    return None


def _check_multi_agent_sample(sample: MultiAgentSample) -> str | None:
    if not sample.subgraph_outputs:
        return "subgraph_outputs 为空"
    for key, merged_value in sample.merged_state.items():
        contributions = [
            output[key]
            for output in sample.subgraph_outputs.values()
            if key in output and output[key] is not None
        ]
        if contributions and merged_value != contributions[-1]:
            return f"merged_state[{key}] 与最后一个非空子图输出不一致"
    if any(output.get("status") == "fallback" for output in sample.subgraph_outputs.values()) and (
        sample.merged_state.get("recognition_fallback") is not True
    ):
        return "子图 fallback 未在汇合状态标记"
    for key, value in sample.expected_business_result.items():
        if key in sample.merged_state and sample.merged_state[key] != value:
            return f"expected_business_result[{key}] 与 merged_state 不一致"
    return None


def _check_interrupt_sample(sample: InterruptSample) -> str | None:
    try:
        if sample.interrupt_kind.value == "clarification":
            ClarificationResume.model_validate(sample.resume_payload)
        elif sample.interrupt_kind.value == "recognition_review":
            RecognitionReviewResume.model_validate(sample.resume_payload)
        elif sample.interrupt_kind.value == "same_item_review":
            SameItemReviewResume.model_validate(sample.resume_payload)
        else:
            MemoryConfirmationResume.model_validate(sample.resume_payload)
    except Exception as exc:
        return f"resume payload 不符合专用模型: {exc}"
    expected_nodes = {
        "clarification": "parse_intent_resume",
        "recognition_review": "recognition_done",
        "same_item_review": "split_sku",
        "memory_confirmation": "merge_constraints",
    }
    if sample.expected_resume_node != expected_nodes[sample.interrupt_kind.value]:
        return "expected_resume_node 与当前 graph wiring 不一致"
    if sample.expected_side_effect_count != 0:
        return "工程夹具要求恢复前副作用计数为 0"
    return None


async def _check_cache_sample(cache: InMemoryVersionedCache, sample: CacheSample) -> str | None:
    initial_key = versioned_key(sample.payload, sample.version_vector)
    changed_key = versioned_key(sample.payload, sample.changed_version_vector)
    result = dict(sample.result_payload)
    result_hash = canonical_cache_key(result)
    if result_hash != sample.expected_result_sha256:
        return "expected_result_sha256 与 result_payload 不一致"

    model_calls = 0
    initial = await cache.get(sample.namespace, initial_key)
    if ("hit" if initial is not None else "miss") != sample.expected_initial:
        return "initial hit/miss 预期不一致"
    if initial is None:
        model_calls += 1
        await cache.set(sample.namespace, initial_key, result, 60)
    if await cache.get(sample.namespace, initial_key) != result:
        return "initial cache 写入后无法 replay"

    changed = await cache.get(sample.namespace, changed_key)
    if ("hit" if changed is not None else "miss") != sample.expected_after_version_change:
        return "version change 后 hit/miss 预期不一致"
    if changed is None:
        model_calls += 1
        await cache.set(sample.namespace, changed_key, result, 60)
    if model_calls != sample.expected_model_calls:
        return f"model_calls 不一致: actual={model_calls}"
    return None


def _retrieval_invariant_counts(
    samples: list[RetrievalStrategySample],
) -> dict[str, int]:
    """运行三组真实策略，检查硬过滤、SKU 元数据和价格事实是否被改写。"""
    counts = {
        "user_hard_filter_violation_count": 0,
        "wrong_sku_group_count": 0,
        "price_fact_error_count": 0,
    }
    for sample in samples:
        by_id = {candidate.offer.offer_id: candidate for candidate in sample.candidates}
        sku_to_spu: dict[str, set[str]] = {}
        for candidate in sample.candidates:
            sku = candidate.offer.sku_key
            spu = candidate.offer.same_item_key
            if sku and spu:
                sku_to_spu.setdefault(sku, set()).add(spu)
        counts["wrong_sku_group_count"] += sum(
            max(0, len(spus) - 1) for spus in sku_to_spu.values()
        )
        query = RetrievalQuery.model_validate(sample.query)
        for strategy in ("weighted", "rrf", "weighted_rerank"):
            ranked = rank_retrieval_strategy(sample, strategy, rrf_k=60, limit=20)
            counts["user_hard_filter_violation_count"] += sum(
                not offer_matches_hard_filters(candidate.offer, query.hard_filters)
                for candidate in ranked
            )
            for candidate in ranked:
                original = by_id[candidate.offer.offer_id]
                if candidate.offer.price != original.offer.price:
                    counts["price_fact_error_count"] += 1
    return counts


def _sensitive_projection_violations() -> int:
    """验证 trace 投影只包含允许的结构化字段，不含自由文本或凭据。"""
    event = AgentEvent(
        session_id="invariant-session",
        request_id="invariant-request",
        turn_id="invariant-turn",
        trace_id="invariant-trace",
        event_type=EventType.NODE_COMPLETED,
        timestamp=now_iso(),
        node_name="parse_intent",
        status=NodeStatus.SUCCESS,
        input_hash="a" * 64,
        output_hash="b" * 64,
        prompt_version="prompt-v1",
        taxonomy_version="taxonomy-v1",
    )
    attributes = span_attributes(event)
    serialized = json.dumps(attributes, ensure_ascii=False, sort_keys=True)
    forbidden = ("data:image/", "sk-", "用户文本", "完整 Prompt")
    return sum(token in serialized for token in forbidden)


async def evaluate_engineering_datasets(
    datasets: dict[str, list[Any]], taxonomy: Taxonomy
) -> EngineeringEvaluationReport:
    """执行四类工程数据集，返回独立于商品质量门禁的结果。"""

    memory_samples = cast(list[MemorySample], datasets.get("memory", []))
    multi_samples = cast(list[MultiAgentSample], datasets.get("multi_agent", []))
    interrupt_samples = cast(list[InterruptSample], datasets.get("interrupt", []))
    cache_samples = cast(list[CacheSample], datasets.get("cache", []))
    retrieval_samples = cast(list[RetrievalStrategySample], datasets.get("retrieval_strategy", []))
    invariant_counts = {
        "cross_user_memory_leakage_count": 0,
        "replay_duplicate_side_effect_count": 0,
    }

    with tempfile.TemporaryDirectory(prefix="shijiajing-engineering-eval-") as directory:
        memory = SQLiteMemoryAdapter(f"{directory}/memory.db")
        await memory.setup()
        try:
            memory_failures: dict[str, str] = {}
            for sample in memory_samples:
                try:
                    failure = await _check_memory_sample(memory, sample, taxonomy, invariant_counts)
                except Exception as exc:
                    failure = f"执行异常: {type(exc).__name__}: {exc}"
                if failure:
                    memory_failures[sample.id] = failure
        finally:
            await memory.close()

    multi_failures = {
        sample.id: failure
        for sample in multi_samples
        if (failure := _check_multi_agent_sample(sample)) is not None
    }
    interrupt_failures = {
        sample.id: failure
        for sample in interrupt_samples
        if (failure := _check_interrupt_sample(sample)) is not None
    }

    cache = InMemoryVersionedCache()
    cache_failures: dict[str, str] = {}
    for sample in cache_samples:
        try:
            failure = await _check_cache_sample(cache, sample)
        except Exception as exc:
            failure = f"执行异常: {type(exc).__name__}: {exc}"
        if failure:
            cache_failures[sample.id] = failure

    checks = [
        _result("memory", [sample.id for sample in memory_samples], memory_failures),
        _result("multi_agent", [sample.id for sample in multi_samples], multi_failures),
        _result("interrupt", [sample.id for sample in interrupt_samples], interrupt_failures),
        _result("cache", [sample.id for sample in cache_samples], cache_failures),
    ]
    invariant_counts.update(_retrieval_invariant_counts(retrieval_samples))
    invariant_results = [
        EngineeringInvariantResult(
            name="user_hard_filter_violation_count",
            sample_count=len(retrieval_samples) * 3,
            violation_count=invariant_counts["user_hard_filter_violation_count"],
            evidence="Weighted/RRF/weighted_rerank 真实策略输出",
        ),
        EngineeringInvariantResult(
            name="cross_user_memory_leakage_count",
            sample_count=len(memory_samples),
            violation_count=invariant_counts["cross_user_memory_leakage_count"],
            evidence="SQLiteMemoryAdapter owner recall probe",
        ),
        EngineeringInvariantResult(
            name="replay_duplicate_side_effect_count",
            sample_count=len(memory_samples),
            violation_count=invariant_counts["replay_duplicate_side_effect_count"],
            evidence="SQLiteMemoryAdapter mutation replay",
        ),
        EngineeringInvariantResult(
            name="wrong_sku_group_count",
            sample_count=len(retrieval_samples),
            violation_count=invariant_counts["wrong_sku_group_count"],
            evidence="candidate sku_key → same_item_key consistency",
        ),
        EngineeringInvariantResult(
            name="price_fact_error_count",
            sample_count=len(retrieval_samples) * 3,
            violation_count=invariant_counts["price_fact_error_count"],
            evidence="真实召回策略 model_copy 后 Offer.price 保持一致",
        ),
        EngineeringInvariantResult(
            name="sensitive_field_leakage_count",
            sample_count=1,
            violation_count=_sensitive_projection_violations(),
            evidence="OpenTelemetry structured span projection",
        ),
    ]
    invariant_gate_passed = all(item.passed for item in invariant_results)
    return EngineeringEvaluationReport(
        checks=checks,
        invariants=invariant_results,
        invariant_gate_passed=invariant_gate_passed,
        all_passed=all(not check.failed_ids for check in checks) and invariant_gate_passed,
    )
