"""二期工程不变量评测数据集的严格行模型。

memory、Multi-Agent、HITL 和缓存数据集验证工程不变量，不参与商品质量指标；
`RetrievalStrategySample` 是独立的策略比较夹具，Gold ID 通过显式 offer 映射提供，
不把 provisional 样例提升为正式发布门禁。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from shijiajing_agent.contracts import (
    InterruptKind,
    MemoryDirective,
    RetrievalCandidate,
    RetrievalQuery,
)
from shijiajing_agent.domain.filters import offer_matches_hard_filters
from shijiajing_agent.domain.retrieval_fusion import ReciprocalRankFusion, WeightedScoreFusion
from shijiajing_agent.domain.retrieval_reranking import CandidateRelevanceReranker
from shijiajing_agent.eval_data import EvalSampleMeta
from shijiajing_agent.ports.retrieval import RetrievalResult


class EngineeringRecorded(BaseModel):
    """工程样本的可选观察结果；当前执行器另写报告，不回填该字段。"""

    model_config = ConfigDict(extra="forbid")

    passed: bool | None = None
    details: dict[str, Any] = Field(default_factory=dict[str, Any])


class MemorySessionSample(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1)
    request_id: str = Field(min_length=1)
    directives: list[MemoryDirective] = Field(min_length=1)


class MemorySample(BaseModel):
    """owner 隔离、覆盖、显式 directive 与 forget 后状态的固定夹具。"""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    owner: str = Field(min_length=1)
    sessions: list[MemorySessionSample] = Field(min_length=1)
    expected_scope: str = Field(min_length=1)
    expected_key: str = Field(min_length=1)
    expected_value: Any
    expected_final_constraints: dict[str, Any] = Field(default_factory=dict[str, Any])
    expected_notices: list[str] = Field(default_factory=list[str])
    expected_after_forget: dict[str, Any] = Field(default_factory=dict[str, Any])
    recorded: EngineeringRecorded | None = None


class MultiAgentSample(BaseModel):
    """子图输入、输出、汇合状态和最终业务结果的固定夹具。"""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    subgraph_input: dict[str, Any]
    subgraph_outputs: dict[str, dict[str, Any]]
    merged_state: dict[str, Any]
    expected_business_result: dict[str, Any]
    recorded: EngineeringRecorded | None = None


class InterruptSample(BaseModel):
    """四类 interrupt 的触发前状态、恢复输入、恢复节点和副作用基线。"""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    interrupt_kind: InterruptKind
    before_state: dict[str, Any]
    interrupt_payload: dict[str, Any]
    resume_payload: dict[str, Any]
    expected_resume_node: str = Field(min_length=1)
    expected_side_effect_count: int = Field(ge=0)
    recorded: EngineeringRecorded | None = None


class CacheSample(BaseModel):
    """完整版本向量、版本变化后的 miss 预期、调用次数和结果摘要。"""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    namespace: str = Field(min_length=1)
    payload: dict[str, Any]
    result_payload: dict[str, Any]
    version_vector: dict[str, str | None]
    expected_initial: Literal["hit", "miss"]
    changed_version_vector: dict[str, str | None]
    expected_after_version_change: Literal["hit", "miss"]
    expected_model_calls: int = Field(ge=0)
    expected_result_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    recorded: EngineeringRecorded | None = None


class RetrievalStrategySample(BaseModel):
    """三种召回策略共享候选集和通道排序的可复现比较夹具。"""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    query: dict[str, Any]
    candidates: list[RetrievalCandidate] = Field(min_length=1)
    channel_orders: dict[str, list[str]] = Field(min_length=1)
    expected_spu_ids: list[str] = Field(default_factory=list[str])
    expected_sku_ids: list[str] = Field(default_factory=list[str])
    expected_top_sku_ids: list[str] = Field(default_factory=list[str])
    gold_spu_by_offer_id: dict[str, str] = Field(default_factory=dict[str, str])
    gold_sku_by_offer_id: dict[str, str] = Field(default_factory=dict[str, str])
    meta: EvalSampleMeta | None = None

    @model_validator(mode="after")
    def _channel_ids_exist(self) -> RetrievalStrategySample:
        candidate_ids = {candidate.offer.offer_id for candidate in self.candidates}
        if len(candidate_ids) != len(self.candidates):
            raise ValueError("candidates 的 offer_id 必须唯一")
        for channel, ordered_ids in self.channel_orders.items():
            if len(set(ordered_ids)) != len(ordered_ids):
                raise ValueError(f"channel_orders[{channel}] 不能包含重复 offer_id")
            missing = set(ordered_ids) - candidate_ids
            if missing:
                raise ValueError(f"channel_orders[{channel}] 包含未知 offer_id: {sorted(missing)}")
        for field_name, mapping in (
            ("gold_spu_by_offer_id", self.gold_spu_by_offer_id),
            ("gold_sku_by_offer_id", self.gold_sku_by_offer_id),
        ):
            unknown = set(mapping) - candidate_ids
            if unknown:
                raise ValueError(f"{field_name} 包含未知 offer_id: {sorted(unknown)}")
        return self


def retrieval_strategy_sample_from_result(
    sample_id: str,
    query: RetrievalQuery | dict[str, Any],
    result: RetrievalResult,
    *,
    expected_spu_ids: list[str],
    expected_sku_ids: list[str],
    expected_top_sku_ids: list[str],
    gold_spu_by_offer_id: dict[str, str] | None = None,
    gold_sku_by_offer_id: dict[str, str] | None = None,
    meta: EvalSampleMeta | None = None,
) -> RetrievalStrategySample:
    """把一次真实 RetrievalResult 固化为策略比较夹具。

    生产适配器返回的是融合候选及每个候选的通道分数；这里按同一分数和
    `offer_id` 稳定排序重建通道顺序，不生成伪造分数。Gold ID 由调用方从
    外部标签目录传入，避免读取 Offer 内的 source key 代替 Gold。
    """

    score_fields: tuple[tuple[str, str], ...] = (
        ("dense", "dense_text_score"),
        ("sparse", "sparse_score"),
        ("image", "image_similarity"),
        ("metadata", "metadata_match"),
    )
    channel_orders: dict[str, list[str]] = {}
    for channel, field_name in score_fields:
        scored: list[tuple[float, str]] = []
        for candidate in result.candidates:
            if candidate.channel_sources and channel not in candidate.channel_sources:
                continue
            score = getattr(candidate, field_name)
            if score is not None:
                scored.append((float(score), candidate.offer.offer_id))
        if scored:
            channel_orders[channel] = [
                offer_id
                for _score, offer_id in sorted(scored, key=lambda item: (-item[0], item[1]))
            ]
    if not channel_orders:
        raise ValueError("RetrievalResult 至少需要一个带分数的检索通道")
    query_model = RetrievalQuery.model_validate(query)
    return RetrievalStrategySample(
        id=sample_id,
        query=query_model.model_dump(mode="json", exclude_none=True),
        candidates=result.candidates,
        channel_orders=channel_orders,
        expected_spu_ids=expected_spu_ids,
        expected_sku_ids=expected_sku_ids,
        expected_top_sku_ids=expected_top_sku_ids,
        gold_spu_by_offer_id=dict(gold_spu_by_offer_id or {}),
        gold_sku_by_offer_id=dict(gold_sku_by_offer_id or {}),
        meta=meta,
    )


class RetrievalStrategyResult(BaseModel):
    """单个召回策略的可审计比较结果。"""

    model_config = ConfigDict(extra="forbid")

    strategy: Literal["weighted", "rrf", "weighted_rerank"]
    sample_count: int = Field(ge=0)
    sku_recall_at_20: float = Field(ge=0, le=1)
    spu_recall_at_20: float = Field(ge=0, le=1)
    mrr_at_10: float = Field(ge=0, le=1)
    hard_filter_satisfaction_rate: float = Field(ge=0, le=1)
    zero_result_rate: float = Field(ge=0, le=1)
    hard_filter_violation_count: int = Field(ge=0)


class RetrievalStrategyReport(BaseModel):
    """weighted 基线、RRF 和 weighted+r­erank 的对比报告。"""

    model_config = ConfigDict(extra="forbid")

    rrf_k: int = Field(ge=1)
    limit: int = Field(ge=1)
    results: list[RetrievalStrategyResult]
    recommended_strategy: Literal["weighted"] = "weighted"


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _strategy_recall(actual: list[str], expected: list[str], limit: int) -> float:
    if not expected:
        return 1.0
    return len(set(actual[:limit]) & set(expected)) / len(set(expected))


def _strategy_mrr(actual: list[str], expected_top: list[str], limit: int) -> float:
    expected = set(expected_top)
    for rank, item in enumerate(actual[:limit], start=1):
        if item in expected:
            return 1.0 / rank
    return 0.0


def _gold_ids_for_ranked(
    ranked: list[RetrievalCandidate],
    mapping: dict[str, str],
    fallback_field: Literal["same_item_key", "sku_key"],
    *,
    allow_legacy_fallback: bool,
) -> list[str]:
    """将候选 Offer 映射为 Gold ID；仅旧 seed 允许 source key 兼容回退。"""

    values: list[str] = []
    for candidate in ranked:
        offer_id = candidate.offer.offer_id
        value = mapping.get(offer_id)
        if value is None and allow_legacy_fallback:
            value = getattr(candidate.offer, fallback_field)
        if value is None and not allow_legacy_fallback:
            raise ValueError(f"策略样本候选缺少 Gold 映射: {offer_id}")
        if value:
            values.append(value)
    return _unique(values)


def _rank_strategy(
    sample: RetrievalStrategySample,
    strategy: Literal["weighted", "rrf", "weighted_rerank"],
    *,
    rrf_k: int,
    limit: int,
) -> list[RetrievalCandidate]:
    by_id = {candidate.offer.offer_id: candidate for candidate in sample.candidates}
    channels = {
        name: [by_id[offer_id] for offer_id in offer_ids]
        for name, offer_ids in sample.channel_orders.items()
    }
    if strategy == "weighted":
        return WeightedScoreFusion().fuse({"all": sample.candidates}, limit)
    if strategy == "rrf":
        return ReciprocalRankFusion(rrf_k).fuse(channels, limit)
    weighted = WeightedScoreFusion().fuse({"all": sample.candidates}, limit)
    return CandidateRelevanceReranker().rerank(
        weighted,
        RetrievalQuery.model_validate(sample.query),
        limit,
    )


def rank_retrieval_strategy(
    sample: RetrievalStrategySample,
    strategy: Literal["weighted", "rrf", "weighted_rerank"],
    *,
    rrf_k: int,
    limit: int,
) -> list[RetrievalCandidate]:
    """供工程不变量评测复用的生产策略入口。"""
    return _rank_strategy(sample, strategy, rrf_k=rrf_k, limit=limit)


def evaluate_retrieval_strategies(
    samples: list[RetrievalStrategySample], *, rrf_k: int = 60, limit: int = 20
) -> RetrievalStrategyReport:
    """运行三组真实策略并返回可复现的离线比较结果。

    `recommended_strategy` 固定为 weighted：本阶段只有比较证据，未获得允许切换默认值
    的正式阻断门禁证据前，生产默认必须保持兼容基线。
    """

    results: list[RetrievalStrategyResult] = []
    for strategy in ("weighted", "rrf", "weighted_rerank"):
        sku_recall: list[float] = []
        spu_recall: list[float] = []
        mrr: list[float] = []
        hard_filter_ok: list[bool] = []
        zero_results = 0
        violations = 0
        for sample in samples:
            ranked = _rank_strategy(sample, strategy, rrf_k=rrf_k, limit=limit)
            allow_legacy_fallback = (
                sample.meta is None
                and not sample.gold_spu_by_offer_id
                and not sample.gold_sku_by_offer_id
            )
            sku_ids = _gold_ids_for_ranked(
                ranked,
                sample.gold_sku_by_offer_id,
                "sku_key",
                allow_legacy_fallback=allow_legacy_fallback,
            )
            spu_ids = _gold_ids_for_ranked(
                ranked,
                sample.gold_spu_by_offer_id,
                "same_item_key",
                allow_legacy_fallback=allow_legacy_fallback,
            )
            sku_recall.append(_strategy_recall(sku_ids, sample.expected_sku_ids, 20))
            spu_recall.append(_strategy_recall(spu_ids, sample.expected_spu_ids, 20))
            mrr.append(_strategy_mrr(sku_ids, sample.expected_top_sku_ids, 10))
            violations_for_sample = sum(
                not offer_matches_hard_filters(
                    candidate.offer, RetrievalQuery.model_validate(sample.query).hard_filters
                )
                for candidate in ranked
            )
            violations += violations_for_sample
            hard_filter_ok.append(violations_for_sample == 0)
            zero_results += int(not ranked)
        n = len(samples)
        results.append(
            RetrievalStrategyResult(
                strategy=strategy,
                sample_count=n,
                sku_recall_at_20=sum(sku_recall) / n if n else 0.0,
                spu_recall_at_20=sum(spu_recall) / n if n else 0.0,
                mrr_at_10=sum(mrr) / n if n else 0.0,
                hard_filter_satisfaction_rate=sum(hard_filter_ok) / n if n else 0.0,
                zero_result_rate=zero_results / n if n else 0.0,
                hard_filter_violation_count=violations,
            )
        )
    return RetrievalStrategyReport(rrf_k=rrf_k, limit=limit, results=results)


def retrieval_strategy_report_to_markdown(report: RetrievalStrategyReport) -> str:
    """把策略比较报告写成供评审使用的 Markdown。"""

    lines = [
        "# Retrieval 策略对比报告",
        "",
        f"- RRF k：{report.rrf_k}",
        f"- limit：{report.limit}",
        f"- 推荐默认：`{report.recommended_strategy}`（正式门禁前保持 weighted）",
        "",
        "| strategy | n | sku_recall_at_20 | spu_recall_at_20 | mrr_at_10 | "
        "hard_filter_satisfaction_rate | zero_result_rate | hard_filter_violation_count |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for result in report.results:
        lines.append(
            f"| {result.strategy} | {result.sample_count} | {result.sku_recall_at_20:.6f} | "
            f"{result.spu_recall_at_20:.6f} | {result.mrr_at_10:.6f} | "
            f"{result.hard_filter_satisfaction_rate:.6f} | {result.zero_result_rate:.6f} | "
            f"{result.hard_filter_violation_count} |"
        )
    lines.extend(
        [
            "",
            "策略来自生产领域实现：WeightedScoreFusion、ReciprocalRankFusion、"
            "CandidateRelevanceReranker。此报告不证明正式线上数据质量，也不改变生产默认配置。",
        ]
    )
    return "\n".join(lines) + "\n"
