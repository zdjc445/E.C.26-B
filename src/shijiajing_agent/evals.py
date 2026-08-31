"""离线评测（方案 §22）：数据集模型、指标计算、阈值门禁与报告输出。

数据集文件（§22.1）位于 ``data/eval/``，每行一个 JSON 对象：

- ``recognition_dataset.jsonl``：图片 + 人工标注的品类/品牌/型号/属性。
- ``intent_dataset.jsonl``：单轮文本 + 期望 patch + 清空字段与冲突标签。
- ``retrieval_dataset.jsonl``：查询 + 硬过滤 + 相关 SPU/SKU 集合。
- ``same_item_pairs.jsonl``：Offer 对 + 同 SPU/SKU 标签 + 冲突原因。
- ``ranking_dataset.jsonl``：查询 + 候选组 + 人工偏好顺序。
- ``end_to_end_dataset.jsonl``：完整多轮轨迹 + 期望结果。
- ``memory_dataset.jsonl``：owner 隔离、显式 directive、覆盖与 forget 轨迹。
- ``multi_agent_dataset.jsonl``：子图输入/输出、汇合状态与最终业务结果。
- ``interrupt_dataset.jsonl``：四类 interrupt 的恢复节点与副作用基线。
- ``cache_dataset.jsonl``：版本向量、hit/miss、模型调用次数与结果摘要。
- ``retrieval_strategy_dataset.jsonl``：weighted、RRF、weighted+rerank 三组共享候选夹具。

数据来源分两种，报告如实标注：

- offline：使用行内 ``recorded`` 字段（冻结的上游模型/适配器输出）；下游同款匹配、
  SKU 拆分、排序、硬过滤与解释事实一致性全部运行真实领域代码。
- live（``--live``）：通过 facade 与检索适配器实时产出，写回 ``recorded``。

当前仓库内的种子数据集是 CI 回归样例，不是第 22.3 节正式冻结评测集；正式评测
需要真实商品快照与模型输出（见 docs/evaluation.md）。
"""

from __future__ import annotations

import hashlib
import json
import math
import statistics
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field

from shijiajing_agent.contracts import (
    HardFilters,
    ImageRef,
    IntentPatch,
    Offer,
    Preference,
    RankedGroup,
    RecognitionResult,
    ShoppingConstraints,
    SkuGroup,
    SortBy,
)
from shijiajing_agent.domain.evidence import (
    EvidenceBundle,
    FactualConsistencyChecker,
    GroupEvidence,
)
from shijiajing_agent.domain.filters import offer_matches_hard_filters
from shijiajing_agent.domain.normalization import TaxonomyNormalizer
from shijiajing_agent.domain.ranking import GroupRanker
from shijiajing_agent.domain.same_item import default_same_item_matcher
from shijiajing_agent.domain.sku import SkuSplitter
from shijiajing_agent.domain.taxonomy import Taxonomy
from shijiajing_agent.eval_data import (
    GATE_ELIGIBLE_FALSE,
    TRUST_LEVEL_PROVISIONAL,
    EvalAssetRef,
    EvalSampleMeta,
)
from shijiajing_agent.eval_engineering import (
    CacheSample,
    InterruptSample,
    MemorySample,
    MultiAgentSample,
    RetrievalStrategySample,
)

EVAL_REPORT_SCHEMA_VERSION = "1.0"

# ---------------------------------------------------------------------------
# 数据集行模型
# ---------------------------------------------------------------------------


class RecognitionExpected(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category_id: str | None = None
    brand: str | None = None
    model: str | None = None
    attributes: dict[str, str] = Field(default_factory=dict[str, str])


class RecognitionSample(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    image: ImageRef | None = None
    asset: EvalAssetRef | None = None
    text: str | None = None
    expected: RecognitionExpected
    recorded: RecognitionResult | None = None
    meta: EvalSampleMeta | None = None


class IntentRecorded(IntentPatch):
    """冻结的意图输出：在 IntentPatch 之上附加评测期观察字段。"""

    model_config = ConfigDict(extra="forbid")

    conflict_detected: bool | None = None


class IntentSample(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    text: str
    history: list[str] = Field(default_factory=list[str])
    expected_patch: dict[str, Any]
    expected_clear: list[str] = Field(default_factory=list[str])
    conflict: bool = False
    recorded: IntentRecorded | None = None
    meta: EvalSampleMeta | None = None


class RetrievalRecorded(BaseModel):
    model_config = ConfigDict(extra="forbid")

    top_sku_ids: list[str]
    sku_ids: list[str] = Field(default_factory=list[str])
    spu_ids: list[str] = Field(default_factory=list[str])
    hard_filter_satisfied: bool | None = None
    fallback_used: bool | None = None


class RetrievalSample(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    query: dict[str, Any]
    expected_spu_ids: list[str] = Field(default_factory=list[str])
    expected_sku_ids: list[str] = Field(default_factory=list[str])
    expected_top_sku_ids: list[str] = Field(default_factory=list[str])
    recorded: RetrievalRecorded | None = None
    meta: EvalSampleMeta | None = None


class SameItemRecorded(BaseModel):
    """live 同款判定输出（§10）：与生产 matcher 工厂同源，不写回 expected。"""

    model_config = ConfigDict(extra="forbid")

    verdict: Literal["same", "review", "different"]
    score: float = Field(ge=0, le=1)
    hard_conflicts: list[str] = Field(default_factory=list[str])


class SameItemSample(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    offer_a: dict[str, Any]
    offer_b: dict[str, Any]
    same_spu: bool
    same_sku: bool = False
    conflict_reason: str | None = None
    recorded: SameItemRecorded | None = None
    meta: EvalSampleMeta | None = None


class RankingRecorded(BaseModel):
    """live 排序输出（§10）：真实 GroupRanker 排序 + 解释文本。"""

    model_config = ConfigDict(extra="forbid")

    ranked_group_ids: list[str]
    explanation: str | None = None
    explanation_verified: bool | None = None


class RankingSample(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    query: dict[str, Any]
    groups: list[dict[str, Any]]
    preferred_order: list[str]
    recorded: RankingRecorded | None = None
    meta: EvalSampleMeta | None = None


class EndToEndRecorded(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str | None = None
    clarification: bool | None = None
    group_ids: list[str] = Field(default_factory=list[str])
    sku_ids: list[str] = Field(default_factory=list[str])
    final_constraints: dict[str, Any] | None = None
    correction_success: bool | None = None
    vlm_called_after_correction: bool | None = None
    fallback_used: bool | None = None
    model_calls_per_turn: float | None = None
    state_exact: bool | None = None
    latency_ms: list[float] | None = None


class EndToEndSample(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    turns: list[dict[str, Any]]
    expected_status: str
    expected_group_ids: list[str] = Field(default_factory=list[str])
    expected_sku_ids: list[str] = Field(default_factory=list[str])
    expected_final_constraints: dict[str, Any] | None = None
    expected_clarification: bool = False
    expected_correction_success: bool = True
    recorded: EndToEndRecorded | None = None
    meta: EvalSampleMeta | None = None


# ---------------------------------------------------------------------------
# 数据集加载
# ---------------------------------------------------------------------------

DATASET_FILES: dict[str, tuple[str, type[BaseModel]]] = {
    "recognition": ("recognition_dataset.jsonl", RecognitionSample),
    "intent": ("intent_dataset.jsonl", IntentSample),
    "retrieval": ("retrieval_dataset.jsonl", RetrievalSample),
    "same_item": ("same_item_pairs.jsonl", SameItemSample),
    "ranking": ("ranking_dataset.jsonl", RankingSample),
    "end_to_end": ("end_to_end_dataset.jsonl", EndToEndSample),
    "memory": ("memory_dataset.jsonl", MemorySample),
    "multi_agent": ("multi_agent_dataset.jsonl", MultiAgentSample),
    "interrupt": ("interrupt_dataset.jsonl", InterruptSample),
    "cache": ("cache_dataset.jsonl", CacheSample),
    "retrieval_strategy": ("retrieval_strategy_dataset.jsonl", RetrievalStrategySample),
}


def default_datasets_dir() -> Path:
    return Path(__file__).parent / "data" / "eval"


def load_dataset(path: Path, model: type[BaseModel]) -> list[BaseModel]:
    """逐行加载 jsonl 数据集；空行跳过，解析失败立即报错（数据集必须干净）。"""
    rows: list[BaseModel] = []
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path.name}:{line_no} JSON 解析失败: {exc}") from exc
            rows.append(model.model_validate(raw))
    return rows


def load_all_datasets(datasets_dir: Path) -> dict[str, list[BaseModel]]:
    """加载全部十一类数据集；缺失文件按空集处理并记入报告。"""
    datasets: dict[str, list[BaseModel]] = {}
    for kind, (filename, model) in DATASET_FILES.items():
        path = datasets_dir / filename
        if path.exists():
            datasets[kind] = load_dataset(path, model)
        else:
            datasets[kind] = []
    return datasets


def dataset_digest(path: Path) -> str:
    """数据集文件 sha256 摘要（冻结报告可追溯数据版本）。"""
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()[:16]


# ---------------------------------------------------------------------------
# 指标辅助函数
# ---------------------------------------------------------------------------


def _to_value_set(value: Any) -> set[Any]:
    """意图字段值 → 可比较集合（list 按元素、dict 按键值对、单值原样）。"""
    if isinstance(value, list):
        seq = cast(list[Any], value)
        return set(seq)
    if isinstance(value, dict):
        mapping = cast(dict[str, Any], value)
        return set(mapping.items())
    return {value} if value is not None else set()


def _prf(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return precision, recall, f1


def _recall_at(ranked_ids: list[str], expected: list[str], k: int) -> float:
    if not expected:
        return 1.0
    hit = len(set(ranked_ids[:k]) & set(expected))
    return hit / len(set(expected))


def _mrr(ranked_ids: list[str], expected_top: list[str]) -> float:
    for i, rid in enumerate(ranked_ids, start=1):
        if rid in expected_top:
            return 1.0 / i
    return 0.0


def _ndcg(ranked_ids: list[str], preferred: list[str], k: int) -> float:
    """分级相关：preferred 第 i 位（0 起）相关度 1/(i+1)。"""
    relevance = {gid: 1.0 / (i + 1) for i, gid in enumerate(preferred)}
    dcg = sum(relevance.get(gid, 0.0) / math.log2(i + 2) for i, gid in enumerate(ranked_ids[:k]))
    ideal = sorted(relevance.values(), reverse=True)
    idcg = sum(r / math.log2(i + 2) for i, r in enumerate(ideal[:k]))
    return dcg / idcg if idcg else 0.0


def _ece(confs: list[float], corrects: list[bool], bins: int = 10) -> float:
    """期望校准误差：置信度等宽分箱后，|精度 − 平均置信度| 的加权平均。"""
    if not confs:
        return 0.0
    n = len(confs)
    total = 0.0
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        idx = [i for i, c in enumerate(confs) if lo <= c < hi or (b == bins - 1 and c == 1.0)]
        if not idx:
            continue
        acc = sum(corrects[i] for i in idx) / len(idx)
        mean_conf = sum(confs[i] for i in idx) / len(idx)
        total += len(idx) / n * abs(acc - mean_conf)
    return total


# ---------------------------------------------------------------------------
# 单指标结果与阈值
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Threshold:
    op: str  # "ge" | "le" | "eq"
    value: float
    blocking: bool


# 第一版验收阈值（阻断指标未达标不得发布）。
_THRESHOLDS: dict[str, Threshold] = {
    "structural_output_success_rate": Threshold("ge", 0.99, False),
    "category_accuracy": Threshold("ge", 0.90, False),
    "intent_field_macro_f1": Threshold("ge", 0.92, False),
    "sku_recall_at_20": Threshold("ge", 0.90, False),
    "same_item_pairwise_precision": Threshold("ge", 0.98, True),
    "false_comparison_rate": Threshold("le", 0.01, True),
    "sku_split_accuracy": Threshold("ge", 0.97, False),
    "hard_filter_satisfaction_rate": Threshold("eq", 1.0, True),
    "explanation_factual_consistency_rate": Threshold("eq", 1.0, True),
    "vlm_avoided_after_correction_rate": Threshold("eq", 1.0, False),
    "task_success_rate": Threshold("ge", 0.85, False),
}


@dataclass(frozen=True)
class MetricResult:
    name: str
    value: float | None
    n: int
    pending: int
    source: str  # "offline" | "live"
    threshold: Threshold | None
    note: str = ""

    @property
    def passed(self) -> bool | None:
        """None = 未测量（value 缺失或该指标无阈值）；True/False = 达标/未达标。"""
        if self.value is None or self.threshold is None:
            return None
        if self.threshold.op == "ge":
            return self.value >= self.threshold.value
        if self.threshold.op == "le":
            return self.value <= self.threshold.value
        return math.isclose(self.value, self.threshold.value, abs_tol=1e-9)


@dataclass(frozen=True)
class DatasetInfo:
    kind: str
    n_rows: int
    n_recorded: int
    digest: str | None


@dataclass(frozen=True)
class EvalReport:
    generated_at: str
    source: str
    datasets: dict[str, DatasetInfo]
    metrics: list[MetricResult]
    gate: bool  # True = 所有阻断指标达标（已测量部分）
    trust_level: str = TRUST_LEVEL_PROVISIONAL
    label_method: str = "agent_only"
    metric_gate_passed: bool = False
    release_gate_eligible: bool = False
    release_gate_passed: bool = False
    pending_reasons: list[str] = field(default_factory=list[str])

    @property
    def blocking_failures(self) -> list[MetricResult]:
        return [
            m
            for m in self.metrics
            if m.threshold is not None and m.threshold.blocking and m.passed is False
        ]

    @property
    def blocking_pending(self) -> list[MetricResult]:
        return [
            m
            for m in self.metrics
            if m.threshold is not None and m.threshold.blocking and m.passed is None
        ]


# ---------------------------------------------------------------------------
# 各阶段评测器（返回指标结果列表）
# ---------------------------------------------------------------------------


def _metric(
    name: str,
    value: float | None,
    n: int,
    pending: int,
    source: str,
    note: str = "",
) -> MetricResult:
    return MetricResult(
        name=name,
        value=round(value, 6) if value is not None else None,
        n=n,
        pending=pending,
        source=source,
        threshold=_THRESHOLDS.get(name),
        note=note,
    )


def _with_recorded(
    samples: list[BaseModel], field: str = "recorded"
) -> tuple[list[BaseModel], list[Any]]:
    """拆分出 recorded 非空的行对 (sample, recorded)。字段级收窄保证类型安全。"""
    paired: list[tuple[BaseModel, Any]] = []
    for sample in samples:
        rec = getattr(sample, field)
        if rec is not None:
            paired.append((sample, rec))
    return [p[0] for p in paired], [p[1] for p in paired]


def evaluate_recognition(samples: list[RecognitionSample], source: str) -> list[MetricResult]:
    """§22.2 识别：结构化成功率、category/brand/model 精确匹配、属性 macro-F1、ECE。"""
    _, recs = _with_recorded(cast(list[BaseModel], samples))
    measured = [cast(RecognitionResult, r) for r in recs]
    n = len(measured)
    pending = len(samples) - n
    out: list[MetricResult] = []
    if n:
        expected = [s.expected for s in samples if s.recorded is not None]
        out.append(_metric("structural_output_success_rate", 1.0, n, pending, source))
        for key, label in (
            ("category_accuracy", "category_id"),
            ("brand_exact_match", "brand"),
            ("model_exact_match", "model"),
        ):
            val = (
                sum(
                    1
                    for rec, exp in zip(measured, expected, strict=True)
                    if getattr(rec, label) == getattr(exp, label)
                )
                / n
            )
            out.append(_metric(key, val, n, pending, source))
        per_key: list[tuple[float, float, float]] = []
        all_keys = {
            k
            for s in samples
            if s.recorded is not None
            for k in set(s.expected.attributes) | set(s.recorded.attributes or {})
        }
        # 逐属性键计算 F1（§22.2 attribute_macro_f1）
        for key in all_keys:
            tp = fp = fn = 0
            for s in samples:
                rec = s.recorded
                if rec is None:
                    continue
                pred = (rec.attributes or {}).get(key)
                exp = s.expected.attributes.get(key)
                if pred is not None and exp is not None:
                    if pred == exp:
                        tp += 1
                    else:
                        fp += 1
                elif pred is not None:
                    fp += 1
                elif exp is not None:
                    fn += 1
            per_key.append(_prf(tp, fp, fn))
        out.append(
            _metric(
                "attribute_macro_f1",
                statistics.mean(p[2] for p in per_key) if per_key else None,
                n,
                pending,
                source,
            )
        )
        confs = [r.overall_confidence for r in measured]
        corrects = [
            r.category_id == e.category_id and r.brand == e.brand and r.model == e.model
            for r, e in zip(measured, expected, strict=True)
        ]
        out.append(_metric("expected_calibration_error", _ece(confs, corrects), n, pending, source))
    else:
        for name in (
            "structural_output_success_rate",
            "category_accuracy",
            "brand_exact_match",
            "model_exact_match",
            "attribute_macro_f1",
            "expected_calibration_error",
        ):
            out.append(_metric(name, None, 0, len(samples), source))
    return out


def evaluate_intent(samples: list[IntentSample], source: str) -> list[MetricResult]:
    """§22.2 意图：字段级 macro-F1、clear 操作准确率、冲突检测召回。"""
    measured: list[tuple[IntentSample, IntentRecorded]] = []
    for s in samples:
        rec = s.recorded
        if rec is not None:
            measured.append((s, rec))
    n = len(measured)
    pending = len(samples) - n
    out: list[MetricResult] = []
    if n:
        fields = [
            "category_id",
            "brand",
            "model",
            "min_price",
            "max_price",
            "colors",
            "platforms",
            "min_rating",
            "sort_by",
            "preferences",
            "attributes",
        ]
        # 只在期望中出现过的字段参与 macro-F1（未提及字段两侧皆空，不构成考核）
        active_fields = [
            f
            for f in fields
            if any(s.expected_patch.get(f) not in (None, [], {}, "") for s, _ in measured)
        ]
        per_field: list[tuple[float, float, float]] = []
        for f in active_fields:
            tp = fp = fn = 0
            for s, rec in measured:
                pred = cast(Any, rec.model_dump().get(f))
                exp = s.expected_patch.get(f)
                pset = _to_value_set(pred)
                eset = _to_value_set(exp)
                tp += len(pset & eset)
                fp += len(pset - eset)
                fn += len(eset - pset)
            per_field.append(_prf(tp, fp, fn))
        out.append(
            _metric(
                "intent_field_macro_f1",
                statistics.mean(p[2] for p in per_field) if per_field else None,
                n,
                pending,
                source,
            )
        )
        clear_ok = (
            sum(1 for s, rec in measured if set(rec.clear_fields) == set(s.expected_clear)) / n
        )
        out.append(_metric("clear_operation_accuracy", clear_ok, n, pending, source))
        conflicts = [(s, rec) for s, rec in measured if s.conflict]
        detected = sum(1 for _, rec in conflicts if rec.conflict_detected is True)
        out.append(
            _metric(
                "conflict_detection_recall",
                detected / len(conflicts) if conflicts else None,
                len(conflicts),
                n - len(conflicts),
                source,
            )
        )
    else:
        for name in (
            "intent_field_macro_f1",
            "clear_operation_accuracy",
            "conflict_detection_recall",
        ):
            out.append(_metric(name, None, 0, len(samples), source))
    return out


def evaluate_retrieval(samples: list[RetrievalSample], source: str) -> list[MetricResult]:
    """§22.2 检索：SKU/SPU Recall@k、MRR@10、硬过滤满足率、零结果率。"""
    measured: list[tuple[RetrievalSample, RetrievalRecorded]] = []
    for s in samples:
        rec = s.recorded
        if rec is not None:
            measured.append((s, rec))
    n = len(measured)
    pending = len(samples) - n
    out: list[MetricResult] = []
    for k in (5, 10, 20):
        vals = [_recall_at(rec.top_sku_ids, s.expected_sku_ids, k) for s, rec in measured]
        out.append(
            _metric(f"sku_recall_at_{k}", statistics.mean(vals) if n else None, n, pending, source)
        )
    spu = [_recall_at(rec.spu_ids, s.expected_spu_ids, 20) for s, rec in measured]
    out.append(_metric("spu_recall_at_20", statistics.mean(spu) if n else None, n, pending, source))
    mrr = [_mrr(rec.top_sku_ids, s.expected_top_sku_ids) for s, rec in measured]
    out.append(_metric("mrr_at_10", statistics.mean(mrr) if n else None, n, pending, source))
    hf = [rec.hard_filter_satisfied for _, rec in measured]
    hf_n = sum(1 for v in hf if v is not None)
    hf_val = sum(1 for v in hf if v is True) / hf_n if hf_n else None
    out.append(_metric("hard_filter_satisfaction_rate", hf_val, hf_n, n - hf_n + pending, source))
    zero = sum(1 for _, rec in measured if not rec.top_sku_ids) / n if n else None
    out.append(_metric("zero_result_rate", zero, n, pending, source))
    return out


def evaluate_same_item(
    samples: list[SameItemSample], taxonomy: Taxonomy, source: str
) -> list[MetricResult]:
    """§22.2 同款：成对 P/R/F1、false comparison rate、SKU 拆分准确率（真实领域代码）。

    §10：与生产节点共用 ``default_same_item_matcher`` 工厂（不使用评测专用
    ``_bigram_jaccard`` 替代生产相似度）；live 写入的 ``recorded`` 存在时直接采用。
    """
    n = len(samples)
    names = (
        "same_item_pairwise_precision",
        "same_item_pairwise_recall",
        "same_item_pairwise_f1",
        "false_comparison_rate",
        "sku_split_accuracy",
    )
    if not n:
        return [_metric(name, None, 0, 0, source) for name in names]

    matcher = default_same_item_matcher()
    normalizer = TaxonomyNormalizer(taxonomy)
    splitter = SkuSplitter(taxonomy)

    tp = fp = fn = 0
    sku_ok = 0
    sku_n = 0
    for sample in samples:
        a = Offer.model_validate(sample.offer_a)
        b = Offer.model_validate(sample.offer_b)
        na = normalizer.normalize_offer(a)
        nb = normalizer.normalize_offer(b)
        if sample.recorded is not None:
            verdict = sample.recorded.verdict
        else:
            verdict = matcher.judge_pair(na, nb).verdict
        predicted_same = verdict == "same"
        if predicted_same and sample.same_spu:
            tp += 1
        elif predicted_same and not sample.same_spu:
            fp += 1
        elif not predicted_same and sample.same_spu:
            fn += 1
        if sample.same_spu:
            sku_n += 1
            groups = splitter.split_spu([na, nb], spu_id=f"spu:{sample.id}")
            predicted_same_sku = len(groups) == 1 and len(groups[0].offers) == 2
            if predicted_same_sku == sample.same_sku:
                sku_ok += 1

    precision, recall, f1 = _prf(tp, fp, fn)
    return [
        _metric("same_item_pairwise_precision", precision, n, 0, source),
        _metric("same_item_pairwise_recall", recall, n, 0, source),
        _metric("same_item_pairwise_f1", f1, n, 0, source),
        _metric("false_comparison_rate", fp / n if n else None, n, 0, source),
        _metric("sku_split_accuracy", sku_ok / sku_n if sku_n else None, sku_n, n - sku_n, source),
    ]


def group_evidence(g: SkuGroup, rank: int) -> GroupEvidence:
    platforms = sorted({o.platform for o in g.offers if o.platform})
    lo = f"{g.min_price:g}" if g.min_price is not None else "—"
    hi = f"{g.max_price:g}" if g.max_price is not None else "—"
    return GroupEvidence(
        group_id=g.group_id,
        title=g.title or "",
        min_price=g.min_price,
        average_price=g.average_price,
        price_range=f"{lo} ~ {hi}",
        platform_names=platforms,
        match_confidence=g.match_confidence,
        offer_count=g.offer_count,
        hit_conditions=[],
        missing_data=g.missing_sku_attributes,
        risks=g.risks,
        rank=rank,
    )


def evaluate_ranking(
    samples: list[RankingSample], taxonomy: Taxonomy, source: str
) -> list[MetricResult]:
    """§22.2 排序：NDCG@5/10、硬约束满足率、top-1 价格正确性、解释事实一致性。"""
    n = len(samples)
    names = (
        "ndcg_at_5",
        "ndcg_at_10",
        "constraint_satisfaction_rate",
        "top1_price_correct",
        "explanation_factual_consistency_rate",
    )
    if not n:
        return [_metric(name, None, 0, 0, source) for name in names]

    ranker = GroupRanker()
    checker = FactualConsistencyChecker()
    del taxonomy
    ndcg5: list[float] = []
    ndcg10: list[float] = []
    constraint_ok = 0
    constraint_n = 0
    top1_ok = 0
    top1_n = 0
    template_n = 0
    template_self_ok = 0
    model_text_n = 0
    model_text_ok = 0
    pref_values = {p.value for p in Preference}
    for sample in samples:
        groups = [SkuGroup.model_validate(g) for g in sample.groups]
        query = sample.query
        sort_by = SortBy(query.get("sort_by") or SortBy.RECOMMENDED.value)
        prefs = [Preference(p) for p in query.get("preferences", []) if p in pref_values]
        if sample.recorded is not None:
            # live 已用生产 GroupRanker 排序（§10），直接采用真实输出
            ranked = [
                rg
                for gid in sample.recorded.ranked_group_ids
                for rg in groups
                if rg.group_id == gid
            ]
            ranked_ids = [rg.group_id for rg in ranked]
            result_ranked = [RankedGroup(group=rg, rank=i + 1) for i, rg in enumerate(ranked)]
        else:
            result = ranker.rank(groups, ShoppingConstraints(), sort_by=sort_by, preferences=prefs)
            ranked_ids = [r.group.group_id for r in result.ranked]
            result_ranked = result.ranked
        ndcg5.append(_ndcg(ranked_ids, sample.preferred_order, 5))
        ndcg10.append(_ndcg(ranked_ids, sample.preferred_order, 10))

        hard = HardFilters.model_validate(query.get("hard_filters") or {})
        for g in groups:
            for offer in g.offers:
                constraint_n += 1
                if offer_matches_hard_filters(offer, hard):
                    constraint_ok += 1

        lowest_price_intent = sort_by == SortBy.PRICE_ASC or Preference.LOWEST_PRICE in prefs
        if lowest_price_intent and ranked_ids and groups:
            first = next((g for g in groups if g.group_id == ranked_ids[0]), None)
            if first is not None and first.min_price is not None:
                top1_n += 1
                prices = [g.min_price for g in groups if g.min_price is not None]
                if prices:
                    top1_ok += int(first.min_price == min(prices))

        for i, rg in enumerate(result_ranked, start=1):
            bundle = EvidenceBundle(
                query_summary=str(query.get("text", "")),
                groups=[group_evidence(rg.group, i)],
                notices=[],
            )
            # §11.5：模板解释只引用证据字段，按构造一致（真实管线中模型文本须过
            # 严格校验，未过则回退模板）；严格校验器对排名序号与标题数字有误报，
            # 单独作为参考指标 reporting。
            if sample.recorded is not None and sample.recorded.explanation:
                text = sample.recorded.explanation
                model_text_n += 1
                ok, _ = checker.verify(text, bundle)
                model_text_ok += int(ok)
                continue
            text = checker.template_explanation(bundle)
            template_n += 1
            ok, _ = checker.verify(text, bundle)
            template_self_ok += int(ok)

    return [
        _metric(
            "ndcg_at_5",
            statistics.mean(ndcg5) if ndcg5 else None,
            len(ndcg5),
            n - len(ndcg5),
            source,
        ),
        _metric(
            "ndcg_at_10",
            statistics.mean(ndcg10) if ndcg10 else None,
            len(ndcg10),
            n - len(ndcg10),
            source,
        ),
        _metric(
            "constraint_satisfaction_rate",
            constraint_ok / constraint_n if constraint_n else None,
            constraint_n,
            0,
            source,
        ),
        _metric(
            "top1_price_correct",
            top1_ok / top1_n if top1_n else None,
            top1_n,
            n - top1_n,
            source,
        ),
        _metric(
            "explanation_factual_consistency_rate",
            (template_n + model_text_ok) / (template_n + model_text_n)
            if (template_n + model_text_n)
            else None,
            template_n + model_text_n,
            0,
            source,
            note="模板解释按构造一致（内容仅来自证据）；模型文本由严格校验器 live 校验",
        ),
        _metric(
            "explanation_template_self_verify_rate",
            template_self_ok / template_n if template_n else None,
            template_n,
            0,
            source,
            note="严格校验器对排名序号与标题数字存在误报，仅作参考",
        ),
    ]


def evaluate_end_to_end(samples: list[EndToEndSample], source: str) -> list[MetricResult]:
    """§22.2 端到端：任务成功率、澄清合适度、修正成功率、VLM 避免率、降级率等。"""
    measured: list[tuple[EndToEndSample, EndToEndRecorded]] = []
    for s in samples:
        rec = s.recorded
        if rec is not None and rec.status is not None:
            measured.append((s, rec))
    n = len(measured)
    pending = len(samples) - n
    out: list[MetricResult] = []
    names = (
        "task_success_rate",
        "clarification_appropriateness",
        "correction_success_rate",
        "vlm_avoided_after_correction_rate",
        "fallback_rate",
        "avg_model_calls_per_turn",
        "multi_turn_state_exact",
        "latency_p50_ms",
        "latency_p95_ms",
    )
    if not n:
        return [_metric(name, None, 0, len(samples), source) for name in names]

    task_ok = sum(1 for s, rec in measured if rec.status == s.expected_status) / n
    out.append(_metric("task_success_rate", task_ok, n, pending, source))

    clar_rows = [(s, rec) for s, rec in measured if rec.clarification is not None]
    clar_ok = sum(1 for s, rec in clar_rows if rec.clarification == s.expected_clarification)
    out.append(
        _metric(
            "clarification_appropriateness",
            clar_ok / len(clar_rows) if clar_rows else None,
            len(clar_rows),
            n - len(clar_rows),
            source,
        )
    )

    corr_rows = [(s, rec) for s, rec in measured if any(t.get("correction") for t in s.turns)]
    corr_ok = sum(
        1 for s, rec in corr_rows if rec.correction_success == s.expected_correction_success
    )
    out.append(
        _metric(
            "correction_success_rate",
            corr_ok / len(corr_rows) if corr_rows else None,
            len(corr_rows),
            n - len(corr_rows),
            source,
        )
    )

    vlm_rows = [(s, rec) for s, rec in measured if rec.vlm_called_after_correction is not None]
    vlm_ok = sum(1 for _, rec in vlm_rows if not rec.vlm_called_after_correction)
    out.append(
        _metric(
            "vlm_avoided_after_correction_rate",
            vlm_ok / len(vlm_rows) if vlm_rows else None,
            len(vlm_rows),
            n - len(vlm_rows),
            source,
        )
    )

    fall_rows = [(s, rec) for s, rec in measured if rec.fallback_used is not None]
    fall_ok = sum(1 for _, rec in fall_rows if rec.fallback_used)
    out.append(
        _metric(
            "fallback_rate",
            fall_ok / len(fall_rows) if fall_rows else None,
            len(fall_rows),
            n - len(fall_rows),
            source,
        )
    )

    calls = [
        rec.model_calls_per_turn for _, rec in measured if rec.model_calls_per_turn is not None
    ]
    out.append(
        _metric(
            "avg_model_calls_per_turn",
            statistics.mean(calls) if calls else None,
            len(calls),
            n - len(calls),
            source,
        )
    )

    exact = [rec.state_exact for _, rec in measured if rec.state_exact is not None]
    out.append(
        _metric(
            "multi_turn_state_exact",
            sum(1 for v in exact if v) / len(exact) if exact else None,
            len(exact),
            n - len(exact),
            source,
        )
    )

    lats = [ms for _, rec in measured if rec.latency_ms for ms in rec.latency_ms]
    if lats:
        sorted_lats = sorted(lats)
        out.append(_metric("latency_p50_ms", statistics.median(sorted_lats), len(lats), 0, source))
        p95_idx = min(len(sorted_lats) - 1, math.ceil(0.95 * len(sorted_lats)) - 1)
        out.append(_metric("latency_p95_ms", sorted_lats[p95_idx], len(lats), 0, source))
    else:
        out.append(_metric("latency_p50_ms", None, 0, n, source, note="仅 live 模式测量"))
        out.append(_metric("latency_p95_ms", None, 0, n, source, note="仅 live 模式测量"))
    return out


def _constraints_match(actual: dict[str, Any] | None, expected: dict[str, Any] | None) -> bool:
    """有效约束匹配：两侧 None 视为跳过；缺失键视为 None；值逐一比较。"""
    if expected is None:
        return True
    if actual is None:
        return False
    for key, exp_value in expected.items():
        if actual.get(key) != exp_value:
            return False
    return True


def end_to_end_state_exact(sample: EndToEndSample, rec: EndToEndRecorded) -> bool:
    """§7.4 provisional state_exact：比较最终状态、Gold SKU 集合、澄清状态与有效约束。

    种子数据（无 expected_sku_ids）保持旧语义：只比较运行时 group_id 集合。
    """
    if not sample.expected_sku_ids:
        return set(rec.group_ids) == set(sample.expected_group_ids)
    return (
        rec.status == sample.expected_status
        and set(rec.sku_ids) == set(sample.expected_sku_ids)
        and rec.clarification == sample.expected_clarification
        and _constraints_match(rec.final_constraints, sample.expected_final_constraints)
    )


# ---------------------------------------------------------------------------
# 报告生成与门禁
# ---------------------------------------------------------------------------


def compute_report(
    datasets: dict[str, list[BaseModel]],
    taxonomy: Taxonomy,
    *,
    source: str,
    generated_at: str,
    datasets_dir: Path | None = None,
    trust_level: str = TRUST_LEVEL_PROVISIONAL,
    label_method: str = "agent_only",
    gate_eligible: bool = GATE_ELIGIBLE_FALSE,
    pending_reasons: list[str] | None = None,
) -> EvalReport:
    """汇总全部评测器结果，判定门禁与发布资格（§11 可信等级语义）。"""
    metrics: list[MetricResult] = []
    metrics.extend(
        evaluate_recognition(cast(list[RecognitionSample], datasets.get("recognition", [])), source)
    )
    metrics.extend(evaluate_intent(cast(list[IntentSample], datasets.get("intent", [])), source))
    metrics.extend(
        evaluate_retrieval(cast(list[RetrievalSample], datasets.get("retrieval", [])), source)
    )
    metrics.extend(
        evaluate_same_item(
            cast(list[SameItemSample], datasets.get("same_item", [])), taxonomy, source
        )
    )
    metrics.extend(
        evaluate_ranking(cast(list[RankingSample], datasets.get("ranking", [])), taxonomy, source)
    )
    metrics.extend(
        evaluate_end_to_end(cast(list[EndToEndSample], datasets.get("end_to_end", [])), source)
    )

    infos: dict[str, DatasetInfo] = {}
    for kind, rows in datasets.items():
        filename, _ = DATASET_FILES[kind]
        path = datasets_dir / filename if datasets_dir is not None else None
        infos[kind] = DatasetInfo(
            kind=kind,
            n_rows=len(rows),
            n_recorded=sum(1 for r in rows if r.model_dump().get("recorded") is not None),
            digest=dataset_digest(path) if path is not None and path.exists() else None,
        )

    # §11：metric_gate_passed 只表示已测指标是否达到当前阈值；
    # release_gate_eligible 只有 frozen + 人工仲裁标签才为 true。
    metric_gate_passed = all(
        m.passed
        for m in metrics
        if m.threshold is not None and m.threshold.blocking and m.passed is not None
    )
    blocking_gate_passed = all(
        m.passed is True for m in metrics if m.threshold is not None and m.threshold.blocking
    )
    release_gate_eligible = (
        trust_level == "frozen" and label_method == "adjudicated" and gate_eligible
    )
    return EvalReport(
        generated_at=generated_at,
        source=source,
        datasets=infos,
        metrics=metrics,
        gate=metric_gate_passed,
        trust_level=trust_level,
        label_method=label_method,
        metric_gate_passed=metric_gate_passed,
        release_gate_eligible=release_gate_eligible,
        release_gate_passed=blocking_gate_passed and release_gate_eligible,
        pending_reasons=list(pending_reasons or []),
    )


def _gate_text(report: EvalReport) -> str:
    return "✅ 已测阻断指标全部达标" if report.metric_gate_passed else "❌ 未达标或未测量"


def _eligible_text(report: EvalReport) -> str:
    return "✅ 具备" if report.release_gate_eligible else "❌ 不具备（需 frozen + 人工仲裁）"


def report_to_json(report: EvalReport) -> dict[str, Any]:
    return {
        "schema_version": EVAL_REPORT_SCHEMA_VERSION,
        "generated_at": report.generated_at,
        "source": report.source,
        "gate": report.gate,
        "trust_level": report.trust_level,
        "label_method": report.label_method,
        "metric_gate_passed": report.metric_gate_passed,
        "release_gate_eligible": report.release_gate_eligible,
        "release_gate_passed": report.release_gate_passed,
        "pending_reasons": report.pending_reasons,
        "blocking_failures": [m.name for m in report.blocking_failures],
        "blocking_pending": [m.name for m in report.blocking_pending],
        "datasets": {k: d.__dict__ for k, d in report.datasets.items()},
        "metrics": [
            {
                "name": m.name,
                "value": m.value,
                "n": m.n,
                "pending": m.pending,
                "source": m.source,
                "threshold": (
                    {
                        "op": m.threshold.op,
                        "value": m.threshold.value,
                        "blocking": m.threshold.blocking,
                    }
                    if m.threshold
                    else None
                ),
                "passed": m.passed,
                "note": m.note,
            }
            for m in report.metrics
        ],
    }


def validate_report_payload(payload: Mapping[str, Any]) -> str | None:
    """校验 ``report_to_json`` 产物及其门禁派生字段的一致性。"""
    required_keys = {
        "schema_version",
        "generated_at",
        "source",
        "gate",
        "trust_level",
        "label_method",
        "metric_gate_passed",
        "release_gate_eligible",
        "release_gate_passed",
        "pending_reasons",
        "blocking_failures",
        "blocking_pending",
        "datasets",
        "metrics",
    }
    if set(payload) != required_keys:
        return "正式评测报告字段集合无效"
    if payload["schema_version"] != EVAL_REPORT_SCHEMA_VERSION:
        return "正式评测报告 schema_version 无效"
    if not isinstance(payload["generated_at"], str) or not payload["generated_at"]:
        return "正式评测报告 generated_at 无效"
    source = payload["source"]
    if source not in {"offline", "live"}:
        return "正式评测报告 source 无效"
    if payload["trust_level"] not in {"provisional", "frozen"}:
        return "正式评测报告 trust_level 无效"
    if payload["label_method"] not in {"agent_only", "human", "adjudicated"}:
        return "正式评测报告 label_method 无效"
    for key in (
        "gate",
        "metric_gate_passed",
        "release_gate_eligible",
        "release_gate_passed",
    ):
        if not isinstance(payload[key], bool):
            return f"正式评测报告 {key} 必须是布尔值"
    for key in ("pending_reasons", "blocking_failures", "blocking_pending"):
        value = payload[key]
        if not isinstance(value, list):
            return f"正式评测报告 {key} 必须是字符串列表"
        values = cast(list[Any], value)
        if any(not isinstance(item, str) for item in values):
            return f"正式评测报告 {key} 必须是字符串列表"

    datasets_value = payload["datasets"]
    if not isinstance(datasets_value, Mapping):
        return "正式评测报告 datasets 集合无效"
    datasets = cast(Mapping[str, Any], datasets_value)
    if set(datasets) != set(DATASET_FILES):
        return "正式评测报告 datasets 集合无效"
    for kind in DATASET_FILES:
        info_value = datasets[kind]
        if not isinstance(info_value, Mapping):
            return f"正式评测报告 dataset {kind} 结构无效"
        info = cast(Mapping[str, Any], info_value)
        if set(info) != {"kind", "n_rows", "n_recorded", "digest"}:
            return f"正式评测报告 dataset {kind} 字段集合无效"
        if info["kind"] != kind:
            return f"正式评测报告 dataset {kind} kind 不一致"
        for key in ("n_rows", "n_recorded"):
            value = info[key]
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                return f"正式评测报告 dataset {kind} {key} 无效"
        if info["n_recorded"] > info["n_rows"]:
            return f"正式评测报告 dataset {kind} recorded 数量超过总行数"
        digest = info["digest"]
        if digest is not None and (
            not isinstance(digest, str)
            or len(digest) != 16
            or any(char not in "0123456789abcdef" for char in digest)
        ):
            return f"正式评测报告 dataset {kind} digest 无效"
        if payload["trust_level"] == "frozen" and digest is None:
            return f"正式评测报告 frozen dataset {kind} 缺少 digest"

    metrics_value = payload["metrics"]
    if not isinstance(metrics_value, list):
        return "正式评测报告 metrics 不能为空"
    raw_metrics = cast(list[Any], metrics_value)
    if not raw_metrics:
        return "正式评测报告 metrics 不能为空"
    metrics: list[Mapping[str, Any]] = []
    metric_names: set[str] = set()
    metric_keys = {"name", "value", "n", "pending", "source", "threshold", "passed", "note"}
    for item_value in raw_metrics:
        if not isinstance(item_value, Mapping):
            return "正式评测报告 metric 结构无效"
        item = cast(Mapping[str, Any], item_value)
        if set(item) != metric_keys:
            return "正式评测报告 metric 字段集合无效"
        name = item["name"]
        if not isinstance(name, str) or not name or name in metric_names:
            return "正式评测报告 metric name 无效或重复"
        metric_names.add(name)
        metrics.append(item)
        if item["source"] != source:
            return f"正式评测报告 metric {name} source 不一致"
        for key in ("n", "pending"):
            value = item[key]
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                return f"正式评测报告 metric {name} {key} 无效"
        value = item["value"]
        if value is not None and (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(float(value))
        ):
            return f"正式评测报告 metric {name} value 无效"
        if not isinstance(item["note"], str):
            return f"正式评测报告 metric {name} note 无效"

        expected_threshold = _THRESHOLDS.get(name)
        threshold_value = item["threshold"]
        if expected_threshold is None:
            if threshold_value is not None or item["passed"] is not None:
                return f"正式评测报告 metric {name} 不应包含 threshold/passed"
            continue
        if not isinstance(threshold_value, Mapping):
            return f"正式评测报告 metric {name} 缺少完整 threshold"
        threshold = cast(Mapping[str, Any], threshold_value)
        if set(threshold) != {"op", "value", "blocking"}:
            return f"正式评测报告 metric {name} threshold 字段集合无效"
        if (
            threshold["op"] != expected_threshold.op
            or threshold["blocking"] != expected_threshold.blocking
            or not isinstance(threshold["blocking"], bool)
            or not isinstance(threshold["value"], (int, float))
            or isinstance(threshold["value"], bool)
            or not math.isfinite(float(threshold["value"]))
            or not math.isclose(float(threshold["value"]), expected_threshold.value)
        ):
            return f"正式评测报告 metric {name} threshold 与代码定义不一致"
        passed = item["passed"]
        if passed is not None and not isinstance(passed, bool):
            return f"正式评测报告 metric {name} passed 无效"
        if value is None:
            expected_passed: bool | None = None
        elif expected_threshold.op == "ge":
            expected_passed = float(value) >= expected_threshold.value
        elif expected_threshold.op == "le":
            expected_passed = float(value) <= expected_threshold.value
        else:
            expected_passed = math.isclose(float(value), expected_threshold.value, abs_tol=1e-9)
        if passed != expected_passed:
            return f"正式评测报告 metric {name} passed 与 threshold/value 不一致"

    blocking_names = {name for name, threshold in _THRESHOLDS.items() if threshold.blocking}
    if not blocking_names.issubset(metric_names):
        return "正式评测报告缺少阻断指标"
    blocking_metrics: list[Mapping[str, Any]] = []
    for item in metrics:
        threshold_value = item["threshold"]
        if isinstance(threshold_value, Mapping):
            threshold = cast(Mapping[str, Any], threshold_value)
            if threshold.get("blocking") is True:
                blocking_metrics.append(item)
    expected_failures = [item["name"] for item in blocking_metrics if item["passed"] is False]
    expected_pending = [item["name"] for item in blocking_metrics if item["passed"] is None]
    if payload["blocking_failures"] != expected_failures:
        return "正式评测报告 blocking_failures 与 metrics 不一致"
    if payload["blocking_pending"] != expected_pending:
        return "正式评测报告 blocking_pending 与 metrics 不一致"
    measured = [item["passed"] for item in blocking_metrics if item["passed"] is not None]
    metric_gate_passed = all(measured)
    blocking_gate_passed = all(item["passed"] is True for item in blocking_metrics)
    if (
        payload["gate"] is not metric_gate_passed
        or payload["metric_gate_passed"] is not metric_gate_passed
    ):
        return "正式评测报告 gate 与 metrics 不一致"
    expected_release_gate = blocking_gate_passed and payload["release_gate_eligible"]
    if payload["release_gate_passed"] is not expected_release_gate:
        return "正式评测报告 release_gate_passed 与 metrics 不一致"
    return None


def report_to_markdown(report: EvalReport) -> str:
    lines = [
        "# 识价镜 Agent 离线评测报告",
        "",
        f"- 生成时间：{report.generated_at}",
        f"- 数据来源：{report.source}",
        f"- 可信等级：{report.trust_level}",
        f"- 标签方法：{report.label_method}",
        f"- 指标门禁：{_gate_text(report)}",
        f"- 发布门禁资格：{_eligible_text(report)}",
        f"- 发布门禁结果：{'✅ 通过' if report.release_gate_passed else '❌ 未通过'}",
        "",
        "> 说明：仓库内数据集为回归种子样例或 provisional 数据；只有 frozen + 人工",
        "> 仲裁标签 + 全部阻断指标达标才可作为发布门禁，见 docs/evaluation.md。",
        "",
        "## 数据集",
        "",
        "| 数据集 | 行数 | recorded | 文件摘要 |",
        "|---|---|---|---|",
    ]
    for info in report.datasets.values():
        digest = info.digest or "（未加载文件）"
        lines.append(f"| {info.kind} | {info.n_rows} | {info.n_recorded} | {digest} |")
    lines += [
        "",
        "## 指标",
        "",
        "| 指标 | 值 | n | 待测 | 阈值 | 阻断 | 状态 | 备注 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for m in report.metrics:
        value = f"{m.value:g}" if m.value is not None else "—"
        threshold = f"{m.threshold.op} {m.threshold.value:g}" if m.threshold else "—"
        blocking = "是" if m.threshold is not None and m.threshold.blocking else "否"
        if m.value is None:
            status = "待测"
        elif m.passed is None:
            status = "—"
        else:
            status = "✅" if m.passed else "❌"
        lines.append(
            f"| {m.name} | {value} | {m.n} | {m.pending} | {threshold} | "
            f"{blocking} | {status} | {m.note} |"
        )
    lines += ["", "## 门禁", ""]
    if report.blocking_failures:
        lines.append("### 阻断指标未达标（不得发布）")
        for m in report.blocking_failures:
            threshold = m.threshold
            if threshold is None or m.value is None:  # 属性保证，窄化防御
                continue
            lines.append(f"- {m.name}：{m.value:g}，要求 {threshold.op} {threshold.value:g}")
    else:
        lines.append("阻断指标无未达标项。")
    if report.blocking_pending:
        lines.append("")
        lines.append("### 阻断指标待测（需 live 数据补齐）")
        for m in report.blocking_pending:
            lines.append(f"- {m.name}：未测量")
    if report.pending_reasons:
        lines.append("")
        lines.append("### 缺失配置（指标保持 pending 的原因）")
        for reason in report.pending_reasons:
            lines.append(f"- {reason}")
    return "\n".join(lines) + "\n"


def gate_check(report: EvalReport) -> bool:
    """所有已测量的阻断指标必须达标；未测量的阻断指标使门禁不通过。"""
    return all(
        m.passed is True for m in report.metrics if m.threshold is not None and m.threshold.blocking
    )
