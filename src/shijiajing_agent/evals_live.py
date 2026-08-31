"""live 评测执行器（Phase 1 方案 §10）：六类 live runner、端口计数包装器、run manifest。

原则：
- ``recorded`` 只来自真实端口执行或明确标识的本地 baseline；不得从 expected 复制。
- 使用 evaluation-only 端口包装器计数（model/vlm/retrieval/explanation 调用次数），
  不修改生产响应协议。
- retrieval 与 end_to_end 通过外部 Gold catalog（offer_labels.jsonl）把 Offer ID 映射到
  Gold SPU/SKU ID，不读取 Offer 内的 Gold 字段。
- 每个 end_to_end sample 使用独立 session 并为每次运行增加 run ID，防止旧 Checkpoint 命中。
- live 输出目录写入 ``run_manifest.json``（§10），记录模型、Prompt、taxonomy、索引、
  参数与代码 commit。
"""

from __future__ import annotations

import hashlib
import statistics
import subprocess
import time
from dataclasses import dataclass, replace
from inspect import isawaitable
from pathlib import Path
from typing import Any, cast

from shijiajing_agent.config import Settings
from shijiajing_agent.contracts import (
    AgentRequest,
    AgentResponse,
    AgentStatus,
    ImageRef,
    IntentPatch,
    Offer,
    Preference,
    RecognitionResult,
    RetrievalQuery,
    ShoppingConstraints,
    SkuGroup,
    SortBy,
    SourcedValue,
)
from shijiajing_agent.domain.constraints import ConstraintMerger
from shijiajing_agent.domain.evidence import EvidenceBundle, FactualConsistencyChecker
from shijiajing_agent.domain.filters import offer_matches_hard_filters
from shijiajing_agent.domain.ranking import GroupRanker
from shijiajing_agent.domain.same_item import default_same_item_matcher
from shijiajing_agent.domain.taxonomy import Taxonomy
from shijiajing_agent.eval_data import (
    AssetMapEntry,
    OfferGoldLabel,
    asset_ref_to_image_ref,
    load_asset_map,
)
from shijiajing_agent.eval_engineering import (
    RetrievalStrategySample,
    retrieval_strategy_sample_from_result,
)
from shijiajing_agent.evals import (
    EndToEndRecorded,
    EndToEndSample,
    IntentRecorded,
    IntentSample,
    RankingRecorded,
    RankingSample,
    RecognitionSample,
    RetrievalRecorded,
    RetrievalSample,
    SameItemRecorded,
    SameItemSample,
    end_to_end_state_exact,
)
from shijiajing_agent.facade import AgentDependencies, AgentFacade
from shijiajing_agent.ports.models import (
    ExplanationModelPort,
    IntentModelPort,
    QueryRewritePort,
    VisionModelPort,
)
from shijiajing_agent.ports.retrieval import ProductRetrievalPort, RetrievalResult

# ---------------------------------------------------------------------------
# 端口计数包装器（§10：evaluation-only，不修改生产响应协议）
# ---------------------------------------------------------------------------


@dataclass
class CallCounts:
    model_calls: int = 0
    vlm_calls: int = 0
    retrieval_calls: int = 0
    retrieval_fallbacks: int = 0
    explanation_calls: int = 0
    query_rewrite_calls: int = 0

    def snapshot(self) -> CallCounts:
        return CallCounts(
            model_calls=self.model_calls,
            vlm_calls=self.vlm_calls,
            retrieval_calls=self.retrieval_calls,
            retrieval_fallbacks=self.retrieval_fallbacks,
            explanation_calls=self.explanation_calls,
            query_rewrite_calls=self.query_rewrite_calls,
        )

    def delta(self, before: CallCounts) -> CallCounts:
        return CallCounts(
            model_calls=self.model_calls - before.model_calls,
            vlm_calls=self.vlm_calls - before.vlm_calls,
            retrieval_calls=self.retrieval_calls - before.retrieval_calls,
            retrieval_fallbacks=self.retrieval_fallbacks - before.retrieval_fallbacks,
            explanation_calls=self.explanation_calls - before.explanation_calls,
            query_rewrite_calls=self.query_rewrite_calls - before.query_rewrite_calls,
        )


class CountedVision:
    def __init__(self, inner: VisionModelPort, counts: CallCounts) -> None:
        self._inner = inner
        self._counts = counts

    async def setup(self) -> None:
        result = self._inner.setup()
        if isawaitable(result):
            await result

    async def close(self) -> None:
        result = self._inner.close()
        if isawaitable(result):
            await result

    async def recognize(self, image: ImageRef, taxonomy: Taxonomy) -> RecognitionResult:
        self._counts.vlm_calls += 1
        self._counts.model_calls += 1
        return await self._inner.recognize(image, taxonomy)


class CountedIntent:
    def __init__(self, inner: IntentModelPort, counts: CallCounts) -> None:
        self._inner = inner
        self._counts = counts

    async def extract_intent(
        self, text: str, prev: ShoppingConstraints | None, taxonomy: Taxonomy
    ) -> IntentPatch:
        self._counts.model_calls += 1
        return await self._inner.extract_intent(text, prev, taxonomy)


class CountedQueryRewrite:
    def __init__(self, inner: QueryRewritePort, counts: CallCounts) -> None:
        self._inner = inner
        self._counts = counts

    async def rewrite(
        self,
        text: str,
        constraints: ShoppingConstraints | None,
        recognition: RecognitionResult | None,
    ) -> RetrievalQuery:
        self._counts.model_calls += 1
        self._counts.query_rewrite_calls += 1
        return await self._inner.rewrite(text, constraints, recognition)


class CountedExplanation:
    def __init__(self, inner: ExplanationModelPort, counts: CallCounts) -> None:
        self._inner = inner
        self._counts = counts

    async def explain(self, bundle: EvidenceBundle) -> str:
        self._counts.model_calls += 1
        self._counts.explanation_calls += 1
        return await self._inner.explain(bundle)


class CountedRetrieval:
    def __init__(self, inner: ProductRetrievalPort, counts: CallCounts) -> None:
        self._inner = inner
        self._counts = counts

    async def setup(self) -> None:
        result = self._inner.setup()
        if isawaitable(result):
            await result

    async def close(self) -> None:
        result = self._inner.close()
        if isawaitable(result):
            await result

    async def search(
        self,
        query: RetrievalQuery,
        *,
        image: ImageRef | None = None,
        top_k: int = 100,
        union_limit: int = 200,
        category_names: dict[str, str] | None = None,
    ) -> RetrievalResult:
        self._counts.retrieval_calls += 1
        result = await self._inner.search(
            query,
            image=image,
            top_k=top_k,
            union_limit=union_limit,
            category_names=category_names,
        )
        if result.fallback_used:
            self._counts.retrieval_fallbacks += 1
        return result


def counted_deps(deps: AgentDependencies, counts: CallCounts) -> AgentDependencies:
    """用计数包装器复制一份依赖（端口响应协议不变）。"""
    return replace(
        deps,
        vision=CountedVision(deps.vision, counts),
        intent=CountedIntent(deps.intent, counts),
        query_rewrite=CountedQueryRewrite(deps.query_rewrite, counts),
        explanation=CountedExplanation(deps.explanation, counts),
        retrieval=CountedRetrieval(deps.retrieval, counts),
    )


# ---------------------------------------------------------------------------
# Gold catalog（offer_id -> Gold 标签）
# ---------------------------------------------------------------------------


def load_gold_catalog(datasets_dir: Path) -> dict[str, OfferGoldLabel]:
    """从 offer_labels.jsonl 加载 Gold catalog（offer_id → OfferGoldLabel）。"""
    from shijiajing_agent.eval_data import OfferGoldLabel, load_jsonl_rows

    path = datasets_dir / "offer_labels.jsonl"
    if not path.exists():
        return {}
    catalog: dict[str, OfferGoldLabel] = {}
    for label in load_jsonl_rows(path, OfferGoldLabel):
        catalog[label.offer_id] = label
    return catalog


# ---------------------------------------------------------------------------
# 六类 live runner
# ---------------------------------------------------------------------------


async def live_recognition(
    sample: RecognitionSample,
    deps: AgentDependencies,
    assets_dir: Path,
    asset_map: dict[str, AssetMapEntry],
) -> RecognitionResult:
    """§10 recognition：解析本地 asset → data URL → VisionModelPort.recognize。"""
    if sample.asset is not None:
        image = asset_ref_to_image_ref(sample.asset, assets_dir, asset_map)
    elif sample.image is not None:
        image = sample.image
    else:
        raise ValueError(f"recognition 样本缺少 image/asset: {sample.id}")
    return await deps.vision.recognize(image, deps.taxonomy)


async def live_intent(sample: IntentSample, deps: AgentDependencies) -> IntentRecorded:
    """§10 intent：顺序重放历史 patch 与约束合并，写入冲突观察字段。"""
    merger = ConstraintMerger(deps.taxonomy)
    prev: ShoppingConstraints | None = None
    for i, history_text in enumerate(sample.history):
        patch = await deps.intent.extract_intent(history_text, prev, deps.taxonomy)
        merged = merger.merge(
            prev=prev,
            vision=None,
            intent=patch,
            correction=None,
            new_subject=False,
            turn_id=f"eval-history-{sample.id}-{i}",
        )
        prev = merged.constraints
    patch = await deps.intent.extract_intent(sample.text, prev, deps.taxonomy)
    merged = merger.merge(
        prev=prev,
        vision=None,
        intent=patch,
        correction=None,
        new_subject=False,
        turn_id=f"eval-{sample.id}",
    )
    return IntentRecorded(
        **patch.model_dump(),
        conflict_detected=bool(merged.conflicts),
    )


def _require_gold_labels(
    offer_ids: list[str], catalog: dict[str, OfferGoldLabel]
) -> dict[str, OfferGoldLabel]:
    missing = [offer_id for offer_id in offer_ids if catalog.get(offer_id) is None]
    if missing:
        raise ValueError(f"Gold catalog 缺少 Offer 映射: {missing[:5]}")
    return {offer_id: catalog[offer_id] for offer_id in dict.fromkeys(offer_ids)}


def _gold_mapping(
    offer_ids: list[str], catalog: dict[str, OfferGoldLabel]
) -> tuple[list[str], list[str]]:
    """Offer ID 列表 → (gold_spu_ids 去重, gold_sku_ids 去重)。"""
    labels = _require_gold_labels(offer_ids, catalog)
    spu_ids: list[str] = []
    sku_ids: list[str] = []
    for offer_id in offer_ids:
        label = labels[offer_id]
        spu = label.gold_spu_id
        sku = label.gold_sku_id
        if spu not in spu_ids:
            spu_ids.append(spu)
        if sku not in sku_ids:
            sku_ids.append(sku)
    return spu_ids, sku_ids


async def live_retrieval(
    sample: RetrievalSample, deps: AgentDependencies, catalog: dict[str, OfferGoldLabel]
) -> RetrievalRecorded:
    """§10 retrieval：真实检索端口执行，通过 Gold catalog 映射 Offer → Gold SPU/SKU。"""
    query = RetrievalQuery.model_validate(sample.query)
    result = await deps.retrieval.search(query, top_k=50, union_limit=100)
    _top_spu, top_sku = _gold_mapping([c.offer.offer_id for c in result.candidates[:50]], catalog)
    all_spu, all_sku = _gold_mapping([c.offer.offer_id for c in result.candidates], catalog)
    hard_ok = all(
        offer_matches_hard_filters(c.offer, query.hard_filters) for c in result.candidates[:50]
    )
    return RetrievalRecorded(
        top_sku_ids=top_sku,
        sku_ids=all_sku,
        spu_ids=all_spu,
        hard_filter_satisfied=hard_ok,
        fallback_used=result.fallback_used or None,
    )


async def live_retrieval_strategy(
    sample: RetrievalStrategySample,
    deps: AgentDependencies,
    catalog: dict[str, OfferGoldLabel],
) -> RetrievalStrategySample:
    """用真实 RetrievalResult 更新策略夹具，并通过 catalog 写入 Gold 映射。"""

    query = RetrievalQuery.model_validate(sample.query)
    result = await deps.retrieval.search(query, top_k=50, union_limit=100)
    gold_spu_by_offer_id: dict[str, str] = {}
    gold_sku_by_offer_id: dict[str, str] = {}
    labels = _require_gold_labels([c.offer.offer_id for c in result.candidates], catalog)
    for candidate in result.candidates:
        offer_id = candidate.offer.offer_id
        label = labels[offer_id]
        gold_spu_by_offer_id[offer_id] = label.gold_spu_id
        gold_sku_by_offer_id[offer_id] = label.gold_sku_id
    return retrieval_strategy_sample_from_result(
        sample.id,
        query,
        result,
        expected_spu_ids=sample.expected_spu_ids,
        expected_sku_ids=sample.expected_sku_ids,
        expected_top_sku_ids=sample.expected_top_sku_ids,
        gold_spu_by_offer_id=gold_spu_by_offer_id,
        gold_sku_by_offer_id=gold_sku_by_offer_id,
        meta=sample.meta,
    )


async def live_same_item(sample: SameItemSample, deps: AgentDependencies) -> SameItemRecorded:
    """§10 same-item：运行与生产节点相同的 matcher 工厂（不使用评测专用相似度）。"""
    from shijiajing_agent.domain.normalization import TaxonomyNormalizer

    a = Offer.model_validate(sample.offer_a)
    b = Offer.model_validate(sample.offer_b)
    matcher = default_same_item_matcher()
    normalizer = TaxonomyNormalizer(deps.taxonomy)
    result = matcher.judge_pair(normalizer.normalize_offer(a), normalizer.normalize_offer(b))
    verdict = result.verdict
    if verdict not in ("same", "review", "different"):
        verdict = "different"
    return SameItemRecorded(
        verdict=verdict,  # type: ignore[reportArgumentType]
        score=result.score,
        hard_conflicts=result.hard_conflicts,
    )


async def live_ranking(
    sample: RankingSample, deps: AgentDependencies, counts: CallCounts
) -> RankingRecorded:
    """§10 ranking：运行生产 GroupRanker；需要解释时调用 explanation port 并保存真实文本。"""
    from shijiajing_agent.evals import group_evidence

    groups = [SkuGroup.model_validate(g) for g in sample.groups]
    query = sample.query
    sort_by = SortBy(query.get("sort_by") or SortBy.RECOMMENDED.value)
    pref_values = {p.value for p in Preference}
    prefs = [Preference(p) for p in query.get("preferences", []) if p in pref_values]
    result = GroupRanker().rank(groups, ShoppingConstraints(), sort_by=sort_by, preferences=prefs)
    ranked_ids = [rg.group.group_id for rg in result.ranked]

    explanation: str | None = None
    verified: bool | None = None
    if result.ranked:
        top = result.ranked[0]
        bundle = EvidenceBundle(
            query_summary=str(query.get("text", "")),
            groups=[group_evidence(top.group, 1)],
            notices=[],
        )
        try:
            text = await deps.explanation.explain(bundle)
            counts.explanation_calls += 1
            counts.model_calls += 1
            explanation = text
            ok, _ = FactualConsistencyChecker().verify(text, bundle)
            verified = bool(ok)
        except Exception:
            explanation = None
            verified = None
    return RankingRecorded(
        ranked_group_ids=ranked_ids,
        explanation=explanation,
        explanation_verified=verified,
    )


def _constraints_to_dict(constraints: ShoppingConstraints | None) -> dict[str, Any]:
    """有效约束 → 可序列化 dict（跳过空值；枚举转 value）。"""
    if constraints is None:
        return {}
    names = (
        "category_id",
        "category_name",
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
    )
    out: dict[str, Any] = {}
    for name in names:
        sv: Any = getattr(constraints, name)
        value: Any = sv.value if isinstance(sv, SourcedValue) else sv
        if value is None:
            continue
        if isinstance(value, (SortBy, Preference)):
            value = value.value
        if isinstance(value, list):
            value = [
                v.value if isinstance(v, (SortBy, Preference)) else v
                for v in cast(list[Any], value)
            ]
        out[name] = value
    return out


def _response_gold_sku_ids(
    response: AgentResponse, catalog: dict[str, OfferGoldLabel]
) -> list[str]:
    ids: list[str] = []
    for rg in response.groups:
        for offer in rg.group.offers:
            label = catalog.get(offer.offer_id)
            sku = label.gold_sku_id if label else offer.offer_id
            if sku not in ids:
                ids.append(sku)
    return ids


async def live_end_to_end(
    sample: EndToEndSample,
    deps: AgentDependencies,
    catalog: dict[str, OfferGoldLabel],
    *,
    run_id: str,
    runtime_facade: AgentFacade | None = None,
) -> EndToEndRecorded:
    """§10 end_to_end：执行 facade，记录每轮延迟、模型/VLM 调用、fallback、约束与 Gold SKU。"""
    counts = CallCounts()
    counted = counted_deps(
        runtime_facade.dependencies if runtime_facade is not None else deps,
        counts,
    )
    facade = AgentFacade(counted)
    latencies: list[float] = []
    per_turn_calls: list[float] = []
    vlm_after_correction: bool | None = None
    fallback_used = False
    last: AgentResponse | None = None
    for i, raw in enumerate(sample.turns):
        request = AgentRequest.model_validate(raw)
        if not request.request_id:
            request = request.model_copy(update={"request_id": f"eval-{sample.id}-t{i}"})
        before = counts.snapshot()
        started = time.perf_counter()
        last = await facade.run(request)
        latencies.append((time.perf_counter() - started) * 1000.0)
        per_turn = counts.delta(before)
        per_turn_calls.append(float(per_turn.model_calls))
        if request.correction is not None:
            vlm_after_correction = per_turn.vlm_calls > 0
        if per_turn.retrieval_fallbacks > 0:
            fallback_used = True
    assert last is not None
    status = last.status.value
    has_correction = any(t.get("correction") for t in sample.turns)
    recorded = EndToEndRecorded(
        status=status,
        clarification=last.status == AgentStatus.CLARIFICATION,
        group_ids=[g.group.group_id for g in last.groups],
        sku_ids=_response_gold_sku_ids(last, catalog),
        final_constraints=_constraints_to_dict(last.effective_constraints),
        correction_success=last.status != AgentStatus.FAILED if has_correction else None,
        vlm_called_after_correction=vlm_after_correction,
        fallback_used=fallback_used or None,
        model_calls_per_turn=(statistics.mean(per_turn_calls) if per_turn_calls else None),
        state_exact=None,
        latency_ms=latencies,
    )
    recorded = recorded.model_copy(update={"state_exact": end_to_end_state_exact(sample, recorded)})
    return recorded


# ---------------------------------------------------------------------------
# run manifest（§10）
# ---------------------------------------------------------------------------


def _git_commit(repo_root: Path) -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        value = out.stdout.strip()
        return value if value else "unknown"
    except Exception:
        return "unknown"


def _prompts_digest(prompts_dir: Path) -> str:
    if not prompts_dir.is_dir():
        return "unknown"
    digest = hashlib.sha256()
    for path in sorted(prompts_dir.iterdir()):
        if path.is_file():
            digest.update(path.name.encode("utf-8"))
            digest.update(path.read_bytes())
    return digest.hexdigest()[:16]


def write_run_manifest(
    out_dir: Path,
    *,
    dataset_id: str,
    settings: Settings,
    taxonomy: Taxonomy,
    generated_at: str,
    run_id: str,
    repo_root: Path,
) -> Path:
    """写入 live 运行清单：模型、Prompt、taxonomy、索引、参数与代码 commit。"""
    index_desc: dict[str, Any]
    if settings.milvus_collection:
        index_desc = {
            "type": "milvus",
            "collection": settings.milvus_collection,
            "milvus_uri": settings.milvus_uri,
        }
    else:
        index_desc = {
            "type": "local_snapshot",
            "path": settings.local_product_snapshot_path,
        }
    manifest = {
        "run_id": run_id,
        "dataset_id": dataset_id,
        "generated_at": generated_at,
        "source": "live",
        "models": {
            "vision": settings.ark_vision_model,
            "text": settings.ark_text_model,
            "embedding": settings.embedding_model,
            "explanation": settings.ark_text_model,
        },
        "prompts": {"digest": _prompts_digest(repo_root / "src" / "shijiajing_agent" / "prompts")},
        "taxonomy_version": taxonomy.taxonomy_version,
        "index": index_desc,
        "params": {
            "same_item_accept_threshold": settings.same_item_accept_threshold,
            "same_item_review_threshold": settings.same_item_review_threshold,
            "retrieval_top_k_per_channel": settings.retrieval_top_k_per_channel,
            "retrieval_union_limit": settings.retrieval_union_limit,
        },
        "code_commit": _git_commit(repo_root),
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "run_manifest.json"
    import json

    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# 批量执行
# ---------------------------------------------------------------------------


def resolve_asset_map(assets_dir: Path | None) -> dict[str, AssetMapEntry]:
    """资产映射解析（同步；异步函数内避免 pathlib 方法调用）。"""
    if assets_dir is None or not assets_dir.is_dir():
        return {}
    return load_asset_map(assets_dir.parent / "asset_map.jsonl")


async def run_live_paths(
    datasets: dict[str, list[Any]],
    deps: AgentDependencies,
    *,
    datasets_dir: Path,
    assets_dir: Path | None,
    run_id: str,
    runtime_facade: AgentFacade | None = None,
) -> dict[str, list[Any]]:
    """执行六类商品 live 路径和可选策略夹具刷新（recognition 依赖 --assets-dir）。"""
    asset_map = resolve_asset_map(Path(assets_dir) if assets_dir is not None else None)
    catalog = load_gold_catalog(datasets_dir)

    for sample in datasets.get("recognition") or []:
        rec = cast(RecognitionSample, sample)
        if assets_dir is None or rec.asset is None:
            continue
        rec.recorded = await live_recognition(rec, deps, assets_dir, asset_map)

    for sample in datasets.get("intent") or []:
        cast(IntentSample, sample).recorded = await live_intent(cast(IntentSample, sample), deps)

    for sample in datasets.get("retrieval") or []:
        rec = cast(RetrievalSample, sample)
        rec.recorded = await live_retrieval(rec, deps, catalog)

    strategy_rows = datasets.get("retrieval_strategy") or []
    for index, sample in enumerate(strategy_rows):
        strategy_rows[index] = await live_retrieval_strategy(
            cast(RetrievalStrategySample, sample), deps, catalog
        )

    for sample in datasets.get("same_item") or []:
        rec = cast(SameItemSample, sample)
        rec.recorded = await live_same_item(rec, deps)

    for sample in datasets.get("ranking") or []:
        rec = cast(RankingSample, sample)
        counts = CallCounts()
        rec.recorded = await live_ranking(rec, deps, counts)

    for sample in datasets.get("end_to_end") or []:
        rec = cast(EndToEndSample, sample)
        # 独立 session + 每次运行 run ID 前缀，防止旧 Checkpoint 命中（§10）
        turns = [
            {**raw, "session_id": f"{run_id}:{raw.get('session_id') or f'wf-{rec.id}'}"}
            for raw in rec.turns
        ]
        rec = rec.model_copy(update={"turns": turns})
        rec.recorded = await live_end_to_end(
            rec,
            deps,
            catalog,
            run_id=run_id,
            runtime_facade=runtime_facade,
        )

    return datasets
