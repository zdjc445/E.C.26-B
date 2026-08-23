"""provisional 数据集生成器（Phase 1 方案 §8）。

输入：offers_snapshot.jsonl + offer_labels.jsonl + asset_inventory.jsonl
     + 私有 asset_map / asset_bindings / offer_source_map，及可选策略比较夹具。
输出：六类评测数据集（可附带策略比较数据集）+ manifest.json + README.md。

生成规则（§8）：
- recognition 从本地图片资产生成，manifest 标明 image_domain=listing_image。
- intent / workflow 用户文本为 Agent 生成，scenario_source=agent_generated。
- same-item 难负例优先同品类、同品牌、型号相近但身份属性冲突的 Offer。
- same-SKU 正样本必须跨平台；同 SPU 不同 SKU 样本至少一个 variant attribute 不同。
- retrieval query 覆盖纯文本、硬品牌/型号、预算、平台、评分与零结果。
- ranking group 从 Gold SKU 分组构建，价格计算复用生产 SkuSplitter。
- workflow 的 session_id / request_id 由 dataset_id + sample_id + turn_index 稳定生成。
- 生成器不写 recorded（真实或本地运行器负责填充）。

全部为确定性函数：相同输入产出字节一致的 JSONL。
"""

from __future__ import annotations

import base64
from collections import defaultdict
from pathlib import Path
from typing import Any

from shijiajing_agent.contracts import (
    ImageRef,
    Offer,
    Preference,
    SellerType,
    SortBy,
)
from shijiajing_agent.domain.normalization import TaxonomyNormalizer
from shijiajing_agent.domain.sku import SkuSplitter
from shijiajing_agent.domain.taxonomy import Taxonomy
from shijiajing_agent.eval_data import (
    AssetBinding,
    DatasetManifest,
    EvalAssetRef,
    EvalSampleMeta,
    OfferGoldLabel,
    OfferSourceMap,
    build_manifest,
    compute_files_sha256,
    load_asset_map,
    load_jsonl_rows,
)
from shijiajing_agent.eval_engineering import RetrievalStrategySample
from shijiajing_agent.evals import (
    IntentSample,
    RankingSample,
    RecognitionExpected,
    RecognitionSample,
    RetrievalSample,
    SameItemSample,
    WorkflowSample,
)

# §4.2 每品类样本数
_PER_CATEGORY = {
    "recognition": 100,
    "intent": 100,
    "retrieval": 50,
    "same_item": 200,  # 每品类 200 对（600 总量按品类均衡拆分见 SAME_ITEM_SPLIT）
    "ranking": 30,
    "workflow": 40,
}
# §4.1 目标品类
TARGET_CATEGORIES = ("headphone", "sneaker", "hair_dryer")
SAME_ITEM_BY_CATEGORY = 200  # 200×3 = 600 对
SAME_ITEM_SKU = 100  # 每品类：同 SKU
SAME_ITEM_SPU = 50  # 每品类：同 SPU 不同 SKU
SAME_ITEM_NEG = 50  # 每品类：不同 SPU 难负例

# 六类数据集文件名（与 evals.DATASET_FILES 保持一致）
DATASET_FILENAMES = {
    "recognition": "recognition_dataset.jsonl",
    "intent": "intent_dataset.jsonl",
    "retrieval": "retrieval_dataset.jsonl",
    "same_item": "same_item_pairs.jsonl",
    "ranking": "ranking_dataset.jsonl",
    "workflow": "workflow_dataset.jsonl",
    "retrieval_strategy": "retrieval_strategy_dataset.jsonl",
}


class GoldIndex:
    """快照 + Gold 标签 + 资产的索引视图。"""

    def __init__(
        self,
        offers: list[Offer],
        labels: list[OfferGoldLabel],
        assets: dict[str, Any],
        asset_bindings: dict[str, str],
        source_map: dict[str, str],
        taxonomy: Taxonomy,
    ) -> None:
        self.offers = offers
        self.labels = labels
        self.assets = assets
        self.asset_bindings = asset_bindings
        self.source_map = source_map
        self.taxonomy = taxonomy
        self.label_by_offer = {label.offer_id: label for label in labels}
        self.offer_by_id = {o.offer_id: o for o in offers}
        self.offer_by_source: dict[str, Offer] = {}
        for offer_id, source_id in source_map.items():
            offer = self.offer_by_id.get(offer_id)
            if offer is not None:
                self.offer_by_source[source_id] = offer
        self.spu_offers: dict[str, list[Offer]] = defaultdict(list)
        self.sku_offers: dict[str, list[Offer]] = defaultdict(list)
        self.spu_skus: dict[str, list[str]] = defaultdict(list)
        for label in labels:
            self.spu_offers[label.gold_spu_id].append(self.offer_by_id[label.offer_id])
            self.sku_offers[label.gold_sku_id].append(self.offer_by_id[label.offer_id])
            if label.gold_sku_id not in self.spu_skus[label.gold_spu_id]:
                self.spu_skus[label.gold_spu_id].append(label.gold_sku_id)
        self.cat_offers: dict[str, list[Offer]] = defaultdict(list)
        for o in offers:
            if o.category_id:
                self.cat_offers[o.category_id].append(o)
        self.spu_by_cat: dict[str, list[str]] = defaultdict(list)
        for label in labels:
            if label.gold_spu_id not in self.spu_by_cat[label.category_id]:
                self.spu_by_cat[label.category_id].append(label.gold_spu_id)

    def split_of_spu(self, spu_id: str) -> str:
        for label in self.labels:
            if label.gold_spu_id == spu_id:
                return label.split
        return "holdout"

    def offer_of_asset(self, asset_id: str) -> Offer | None:
        source_id = self.asset_bindings.get(asset_id)
        if source_id is None:
            return None
        return self.offer_by_source.get(source_id)

    def meta(
        self, split: str, category_id: str, subject_ids: list[str], source_refs: list[str]
    ) -> EvalSampleMeta:
        return EvalSampleMeta(
            dataset_version="1.0.0",
            split=split,  # type: ignore[arg-type]
            category_id=category_id,
            subject_ids=subject_ids,
            source_refs=sorted(set(source_refs)),
            label_source="agent",
        )


# ---------------------------------------------------------------------------
# 数据集生成
# ---------------------------------------------------------------------------


def _data_url(asset: Any, assets_dir: Path) -> str:
    path = assets_dir / asset.local_path
    data = path.read_bytes()
    return f"data:{asset.content_type.value};base64,{base64.b64encode(data).decode('ascii')}"


def _gen_recognition(idx: GoldIndex, assets_dir: Path) -> list[RecognitionSample]:
    samples: list[RecognitionSample] = []
    for category_id in TARGET_CATEGORIES:
        target = _PER_CATEGORY["recognition"]
        made = 0
        for asset_id in sorted(idx.asset_bindings):
            if made >= target:
                break
            if not asset_id.startswith(f"ast-{category_id}-"):
                continue
            offer = idx.offer_of_asset(asset_id)
            label = idx.label_by_offer.get(offer.offer_id) if offer else None
            if offer is None or label is None:
                continue
            asset = idx.assets.get(asset_id)
            if asset is None:
                continue
            expected_attrs = dict(offer.identity_attributes)
            expected_attrs.update(offer.variant_attributes)
            samples.append(
                RecognitionSample(
                    id=f"rec-sim-{category_id}-{made:03d}",
                    asset=EvalAssetRef(
                        asset_id=asset_id,
                        content_type=asset.content_type,
                        sha256=asset.sha256,
                    ),
                    expected=RecognitionExpected(
                        category_id=category_id,
                        brand=offer.brand,
                        model=offer.model,
                        attributes=expected_attrs,
                    ),
                    meta=idx.meta(
                        label.split,
                        category_id,
                        [label.gold_spu_id],
                        [idx.source_map.get(offer.offer_id, "")] if offer.offer_id else [],
                    ),
                )
            )
            made += 1
        if made != target:
            raise ValueError(f"recognition {category_id}: 期望 {target} 条，实际 {made}")
    return samples


def _gen_intent(idx: GoldIndex) -> list[IntentSample]:
    samples: list[IntentSample] = []
    for category_id in TARGET_CATEGORIES:
        spus = idx.spu_by_cat.get(category_id, [])
        if not spus:
            continue
        target = _PER_CATEGORY["intent"]
        noun = _NOUNS[category_id]
        for i in range(target):
            spu = spus[i % len(spus)]
            offers = idx.spu_offers[spu]
            label = idx.label_by_offer.get(offers[0].offer_id)
            assert label is not None
            brand = offers[0].brand or ""
            model = offers[0].model or ""
            base_price = min((o.price for o in offers if o.price is not None), default=500.0)
            budget = round(base_price * 0.8)
            source_refs = [
                idx.source_map[o.offer_id] for o in offers if o.offer_id in idx.source_map
            ]
            scenario = i % 5
            sid = f"intent-sim-{category_id}-{i:03d}"
            if scenario == 0:  # 新增
                samples.append(
                    IntentSample(
                        id=sid,
                        text=f"帮我找{brand} {model} {noun}，预算{budget}以内",
                        history=[],
                        expected_patch={
                            "category_id": category_id,
                            "brand": brand,
                            "model": model,
                            "max_price": float(budget),
                        },
                        meta=idx.meta(label.split, category_id, [spu], source_refs),
                    )
                )
            elif scenario == 1:  # 修改
                samples.append(
                    IntentSample(
                        id=sid,
                        text=f"预算改成{budget + 200}",
                        history=[f"我要买{brand} {model}"],
                        expected_patch={"max_price": float(budget + 200)},
                        meta=idx.meta(label.split, category_id, [spu], source_refs),
                    )
                )
            elif scenario == 2:  # 清空
                samples.append(
                    IntentSample(
                        id=sid,
                        text="颜色无所谓了",
                        history=[f"要{brand} {model}，黑色"],
                        expected_patch={},
                        expected_clear=["colors"],
                        meta=idx.meta(label.split, category_id, [spu], source_refs),
                    )
                )
            elif scenario == 3:  # 冲突
                samples.append(
                    IntentSample(
                        id=sid,
                        text=f"预算改成{budget + 500}",
                        history=[f"预算{budget}以内"],
                        expected_patch={"max_price": float(budget + 500)},
                        conflict=True,
                        meta=idx.meta(label.split, category_id, [spu], source_refs),
                    )
                )
            else:  # 偏好取消
                samples.append(
                    IntentSample(
                        id=sid,
                        text="不用官方店了",
                        history=["优先官方旗舰店"],
                        expected_patch={
                            "preferences": None,
                            "cancelled_preferences": ["official_store"],
                        },
                        meta=idx.meta(label.split, category_id, [spu], source_refs),
                    )
                )
    return samples


_NOUNS = {"headphone": "耳机", "sneaker": "运动鞋", "hair_dryer": "吹风机"}


def _gen_retrieval(idx: GoldIndex) -> list[RetrievalSample]:
    """每品类 50 条：文本/硬品牌型号/预算/近型号干扰/平台/评分/零结果全覆盖。"""
    samples: list[RetrievalSample] = []
    for category_id in TARGET_CATEGORIES:
        spus = idx.spu_by_cat.get(category_id, [])
        target = _PER_CATEGORY["retrieval"]
        noun = _NOUNS[category_id]
        for i in range(target):
            spu = spus[i % len(spus)]
            offers = idx.spu_offers[spu]
            label = idx.label_by_offer.get(offers[0].offer_id)
            assert label is not None
            brand = offers[0].brand or ""
            model = offers[0].model or ""
            sku_ids = list(idx.spu_skus[spu])
            source_refs = [
                idx.source_map[o.offer_id] for o in offers if o.offer_id in idx.source_map
            ]
            scenario = i % 5
            sid = f"ret-sim-{category_id}-{i:03d}"
            if scenario == 0:  # 纯文本
                query: dict[str, Any] = {
                    "query_text": f"{brand} {model} {noun}",
                    "hard_filters": {"category_id": category_id},
                }
            elif scenario == 1:  # 硬品牌/型号
                query = {
                    "query_text": f"{brand} {model} {noun}",
                    "hard_filters": {"category_id": category_id, "brand": brand, "model": model},
                }
            elif scenario == 2:  # 预算
                base = min((o.price for o in offers if o.price is not None), default=500.0)
                query = {
                    "query_text": f"{brand} {noun}",
                    "hard_filters": {
                        "category_id": category_id,
                        "max_price": round(base * 1.5, 2),
                    },
                }
            elif scenario == 3:  # 近型号干扰：期望只命中目标型号
                near = _near_model(idx, category_id, brand, model)
                expected_spu = _find_spu_by_model(idx, category_id, brand, near)
                if expected_spu is not None and expected_spu != spu:
                    sku_ids = list(idx.spu_skus[expected_spu])
                    spu = expected_spu
                query = {
                    "query_text": f"{brand} {near} {noun}",
                    "hard_filters": {"category_id": category_id, "brand": brand, "model": near},
                }
            else:  # 混合硬过滤：平台 / 评分 / 零结果
                sub = i % 3
                if sub == 0:
                    query = {
                        "query_text": f"{brand} {model} {noun}",
                        "hard_filters": {"category_id": category_id, "platforms": ["jd"]},
                    }
                elif sub == 1:
                    query = {
                        "query_text": f"{brand} {model} {noun}",
                        "hard_filters": {"category_id": category_id, "min_rating": 4.5},
                    }
                else:
                    # 零结果：不存在的品牌（taxonomy 无别名映射，不会命中任何 SPU）
                    query = {
                        "query_text": f"PhantomBrand {noun}",
                        "hard_filters": {"category_id": category_id},
                    }
                    sku_ids = []
                    spu = ""
            samples.append(
                RetrievalSample(
                    id=sid,
                    query=query,
                    expected_spu_ids=[spu] if spu else [],
                    expected_sku_ids=list(sku_ids),
                    expected_top_sku_ids=[sku_ids[0]] if sku_ids else [],
                    meta=idx.meta(label.split, category_id, [spu] if spu else [], source_refs),
                )
            )
    return samples


def _near_model(idx: GoldIndex, category_id: str, brand: str, model: str) -> str:
    """同品牌相邻型号（按品牌模型名确定性排序），不存在则返回自身。"""
    models = _brand_models(idx, category_id, brand)
    if model in models:
        pos = models.index(model)
        if pos + 1 < len(models):
            return models[pos + 1]
        if pos > 0:
            return models[pos - 1]
    return model


def _brand_models(idx: GoldIndex, category_id: str, brand: str) -> list[str]:
    seen: list[str] = []
    for spu in idx.spu_by_cat.get(category_id, []):
        offers = idx.spu_offers[spu]
        if offers and offers[0].brand == brand:
            m = offers[0].model or ""
            if m and m not in seen:
                seen.append(m)
    return sorted(seen)


def _find_spu_by_model(idx: GoldIndex, category_id: str, brand: str, model: str) -> str | None:
    for spu in idx.spu_by_cat.get(category_id, []):
        offers = idx.spu_offers[spu]
        if offers and offers[0].brand == brand and offers[0].model == model:
            return spu
    return None


def _gen_same_item(idx: GoldIndex) -> list[SameItemSample]:
    samples: list[SameItemSample] = []
    for category_id in TARGET_CATEGORIES:
        spus = idx.spu_by_cat.get(category_id, [])
        # 1) 同 SKU 跨平台（每品类 100 对）
        sku_pairs = 0
        for spu in spus:
            if sku_pairs >= SAME_ITEM_SKU:
                break
            for sku_id in idx.spu_skus[spu]:
                if sku_pairs >= SAME_ITEM_SKU:
                    break
                offers = idx.sku_offers[sku_id]
                by_platform: dict[str, Offer] = {}
                for o in offers:
                    by_platform.setdefault(o.platform or "", o)
                if len(by_platform) < 2:
                    continue
                platforms = sorted(by_platform)
                a, b = by_platform[platforms[0]], by_platform[platforms[1]]
                label = idx.label_by_offer[a.offer_id]
                samples.append(
                    SameItemSample(
                        id=f"si-sim-{category_id}-sku-{sku_pairs:03d}",
                        offer_a=a.model_dump(exclude_none=True),
                        offer_b=b.model_dump(exclude_none=True),
                        same_spu=True,
                        same_sku=True,
                        meta=idx.meta(
                            label.split,
                            category_id,
                            [spu],
                            [idx.source_map[a.offer_id], idx.source_map[b.offer_id]],
                        ),
                    )
                )
                sku_pairs += 1
        if sku_pairs != SAME_ITEM_SKU:
            raise ValueError(
                f"same_item {category_id}: 同 SKU 跨平台对不足（{sku_pairs}/{SAME_ITEM_SKU}）"
            )
        # 2) 同 SPU 不同 SKU（每品类 50 对）
        spu_pairs = 0
        for spu in spus:
            if spu_pairs >= SAME_ITEM_SPU:
                break
            sku_ids = idx.spu_skus[spu]
            if len(sku_ids) < 2:
                continue
            a_offer = idx.sku_offers[sku_ids[0]][0]
            b_offer = idx.sku_offers[sku_ids[1]][0]
            label = idx.label_by_offer[a_offer.offer_id]
            samples.append(
                SameItemSample(
                    id=f"si-sim-{category_id}-spu-{spu_pairs:03d}",
                    offer_a=a_offer.model_dump(exclude_none=True),
                    offer_b=b_offer.model_dump(exclude_none=True),
                    same_spu=True,
                    same_sku=False,
                    conflict_reason="同 SPU 不同 SKU（至少一个 variant attribute 不同）",
                    meta=idx.meta(
                        label.split,
                        category_id,
                        [spu],
                        [idx.source_map[a_offer.offer_id], idx.source_map[b_offer.offer_id]],
                    ),
                )
            )
            spu_pairs += 1
        if spu_pairs != SAME_ITEM_SPU:
            raise ValueError(
                f"same_item {category_id}: 同 SPU 不同 SKU 对不足（{spu_pairs}/{SAME_ITEM_SPU}）"
            )
        # 3) 不同 SPU 难负例：同品类同品牌、型号相近（每品类 50 对，同 split 约束）
        candidates: list[tuple[str, str]] = []
        for spu in spus:
            for other in spus:
                if other <= spu:
                    continue
                a_offers, b_offers = idx.spu_offers[spu], idx.spu_offers[other]
                if not a_offers or not b_offers:
                    continue
                if a_offers[0].brand != b_offers[0].brand:
                    continue
                if a_offers[0].model == b_offers[0].model:
                    continue
                label_a = idx.label_by_offer[a_offers[0].offer_id]
                label_b = idx.label_by_offer[b_offers[0].offer_id]
                if label_a.split != label_b.split:
                    continue  # §4.3：负样本对只能从同一个 split 内选择
                candidates.append((spu, other))
        for neg_pairs, (spu, other) in enumerate(sorted(candidates)[:SAME_ITEM_NEG]):
            a_offers, b_offers = idx.spu_offers[spu], idx.spu_offers[other]
            a, b = a_offers[0], b_offers[0]
            label_a = idx.label_by_offer[a.offer_id]
            samples.append(
                SameItemSample(
                    id=f"si-sim-{category_id}-neg-{neg_pairs:03d}",
                    offer_a=a.model_dump(exclude_none=True),
                    offer_b=b.model_dump(exclude_none=True),
                    same_spu=False,
                    same_sku=False,
                    conflict_reason="同品牌近型号但为不同商品（身份/型号冲突）",
                    meta=idx.meta(
                        label_a.split,
                        category_id,
                        [spu, other],
                        [idx.source_map[a.offer_id], idx.source_map[b.offer_id]],
                    ),
                )
            )
        if len(candidates) < SAME_ITEM_NEG:
            raise ValueError(
                f"same_item {category_id}: 难负例不足（{len(candidates)}/{SAME_ITEM_NEG}）"
            )
    return samples


def _gen_ranking(idx: GoldIndex, taxonomy: Taxonomy) -> list[RankingSample]:
    samples: list[RankingSample] = []
    normalizer = TaxonomyNormalizer(taxonomy)
    splitter = SkuSplitter(taxonomy)
    for category_id in TARGET_CATEGORIES:
        spus = idx.spu_by_cat.get(category_id, [])
        target = _PER_CATEGORY["ranking"]
        for i in range(target):
            spu = spus[i % len(spus)]
            offers = idx.spu_offers[spu]
            label = idx.label_by_offer.get(offers[0].offer_id)
            assert label is not None
            brand = offers[0].brand or ""
            model = offers[0].model or ""
            source_refs = [
                idx.source_map[o.offer_id] for o in offers if o.offer_id in idx.source_map
            ]
            scenario = i % 3
            if scenario == 0:
                sort_by, prefs = SortBy.PRICE_ASC, [Preference.LOWEST_PRICE]
            elif scenario == 1:
                sort_by, prefs = SortBy.RATING_DESC, [Preference.HIGH_RATING]
            else:
                sort_by, prefs = SortBy.RECOMMENDED, [Preference.OFFICIAL_STORE]
            members = [normalizer.normalize_offer(o) for o in offers]
            groups = splitter.split_spu(members, spu_id=spu)
            group_dicts = [g.model_dump(exclude_none=True) for g in groups]
            preferred = _preferred_order(groups, sort_by, prefs)
            samples.append(
                RankingSample(
                    id=f"rank-sim-{category_id}-{i:03d}",
                    query={
                        "text": f"{brand} {model} 比价",
                        "sort_by": sort_by.value,
                        "preferences": [p.value for p in prefs],
                        "hard_filters": {"category_id": category_id},
                    },
                    groups=group_dicts,
                    preferred_order=preferred,
                    meta=idx.meta(label.split, category_id, [spu], source_refs),
                )
            )
    return samples


def _preferred_order(groups: list[Any], sort_by: SortBy, prefs: list[Preference]) -> list[str]:
    """Gold 偏好顺序：按意图主维度确定性排序（价格/评分/官方店）。"""

    def rating(g: Any) -> float:
        return (g.offers[0].rating or -1.0) if g.offers and g.offers[0].rating else -1.0

    def trust(g: Any) -> float:
        if not g.offers:
            return 0.0
        return max(
            {
                SellerType.OFFICIAL: 1.0,
                SellerType.SELF_OPERATED: 0.85,
                SellerType.THIRD_PARTY: 0.5,
                SellerType.UNKNOWN: 0.3,
            }.get(o.seller_type, 0.3)
            for o in g.offers
        )

    def by_price(g: Any) -> tuple[float, str]:
        return (g.min_price if g.min_price is not None else float("inf"), g.group_id)

    def by_rating(g: Any) -> tuple[float, str]:
        return (-rating(g), g.group_id)

    def by_trust(g: Any) -> tuple[float, str]:
        return (-trust(g), g.group_id)

    def by_id(g: Any) -> tuple[str]:
        return (g.group_id,)

    if sort_by == SortBy.PRICE_ASC or Preference.LOWEST_PRICE in prefs:
        key = by_price
    elif sort_by == SortBy.RATING_DESC or Preference.HIGH_RATING in prefs:
        key = by_rating
    elif Preference.OFFICIAL_STORE in prefs:
        key = by_trust
    else:
        key = by_id
    return [g.group_id for g in sorted(groups, key=key)]


def _gen_workflow(idx: GoldIndex, assets_dir: Path, dataset_id: str) -> list[WorkflowSample]:
    samples: list[WorkflowSample] = []
    for category_id in TARGET_CATEGORIES:
        spus = idx.spu_by_cat.get(category_id, [])
        target = _PER_CATEGORY["workflow"]
        noun = _NOUNS[category_id]
        for i in range(target):
            spu = spus[i % len(spus)]
            offers = idx.spu_offers[spu]
            label = idx.label_by_offer.get(offers[0].offer_id)
            assert label is not None
            brand = offers[0].brand or ""
            model = offers[0].model or ""
            sku_ids = idx.spu_skus[spu]
            source_refs = [
                idx.source_map[o.offer_id] for o in offers if o.offer_id in idx.source_map
            ]
            sample_id = f"wf-sim-{category_id}-{i:03d}"
            session_id = f"{dataset_id}-{sample_id}"
            scenario = i % 5
            if scenario == 0:  # 文本
                turns = [
                    {
                        "session_id": session_id,
                        "request_id": f"{session_id}-t0",
                        "text": f"{brand} {model} {noun}",
                    }
                ]
                expected_status = "success"
                clarification = False
            elif scenario == 1:  # 图片
                asset_id = _asset_for_offer(idx, offers[0])
                turns = [
                    {
                        "session_id": session_id,
                        "request_id": f"{session_id}-t0",
                        "text": None,
                        "image": _image_turn(idx, asset_id, assets_dir),
                    }
                ]
                expected_status = "success"
                clarification = False
            elif scenario == 2:  # 多轮澄清
                turns = [
                    {
                        "session_id": session_id,
                        "request_id": f"{session_id}-t0",
                        "text": f"帮我看看{noun}",
                    },
                    {
                        "session_id": session_id,
                        "request_id": f"{session_id}-t1",
                        "text": f"{brand} {model}",
                    },
                ]
                expected_status = "success"
                clarification = False
            elif scenario == 3:  # 修正
                turns = [
                    {
                        "session_id": session_id,
                        "request_id": f"{session_id}-t0",
                        "text": "帮我看看这个",
                    },
                    {
                        "session_id": session_id,
                        "request_id": f"{session_id}-t1",
                        "correction": {
                            "recognition_id": f"rec-{sample_id}",
                            "category_id": category_id,
                            "brand": brand,
                            "model": model,
                        },
                    },
                ]
                expected_status = "success"
                clarification = False
            else:  # 降级：过低预算 → 无结果
                turns = [
                    {
                        "session_id": session_id,
                        "request_id": f"{session_id}-t0",
                        "text": f"{brand} {model} 100元以内",
                    }
                ]
                expected_status = "no_results"
                clarification = False
            constraints: dict[str, Any] = {
                "category_id": category_id,
                "brand": brand,
                "model": model,
            }
            if scenario == 4:
                constraints["max_price"] = 100.0
            samples.append(
                WorkflowSample(
                    id=sample_id,
                    turns=turns,
                    expected_status=expected_status,
                    expected_group_ids=[],
                    expected_sku_ids=list(sku_ids) if expected_status == "success" else [],
                    expected_final_constraints=constraints,
                    expected_clarification=clarification,
                    expected_correction_success=True,
                    meta=idx.meta(label.split, category_id, [spu], source_refs),
                )
            )
    return samples


def _asset_for_offer(idx: GoldIndex, offer: Offer) -> str:
    """找绑定到该 offer 的资产；依次回退：同 offer → 同 SPU 其他 offer → 品类任意资产。"""
    label = idx.label_by_offer.get(offer.offer_id)
    spu_id = label.gold_spu_id if label else None
    candidates: list[Offer] = [offer]
    if spu_id is not None:
        candidates.extend(idx.spu_offers.get(spu_id, []))
    for candidate in candidates:
        source_id = idx.source_map.get(candidate.offer_id)
        if source_id is None:
            continue
        for asset_id, bound in idx.asset_bindings.items():
            if bound == source_id:
                return asset_id
    # 回退：品类首个资产（仍为同一品类的主图）
    category_id = offer.category_id or ""
    for asset_id in sorted(idx.asset_bindings):
        if asset_id.startswith(f"ast-{category_id}-"):
            return asset_id
    return ""


def _image_turn(idx: GoldIndex, asset_id: str, assets_dir: Path) -> dict[str, Any]:
    asset = idx.assets.get(asset_id)
    if asset is None:
        raise ValueError(f"workflow 图片轮缺少资产: {asset_id}")
    return ImageRef(
        image_id=asset_id,
        uri=_data_url(asset, assets_dir),
        content_type=asset.content_type,
        sha256=asset.sha256,
    ).model_dump()


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------


def generate_datasets(
    datasets_dir: Path,
    *,
    snapshot_path: Path,
    labels_path: Path,
    assets_path: Path,
    asset_map_path: Path,
    asset_bindings_path: Path,
    offer_source_map_path: Path,
    assets_dir: Path,
    dataset_id: str,
    dataset_version: str,
    as_of: str,
    created_at: str,
    taxonomy: Taxonomy,
    retrieval_strategy_path: Path | None = None,
) -> DatasetManifest:
    """生成六类数据集、可选策略夹具与 manifest（§8）。输出全部确定性。"""
    offers = [Offer.model_validate(r) for r in load_jsonl_rows(snapshot_path, Offer)]
    labels = [
        OfferGoldLabel.model_validate(r) for r in load_jsonl_rows(labels_path, OfferGoldLabel)
    ]
    asset_map = load_asset_map(asset_map_path)
    bindings = {
        row.asset_id: row.source_id for row in load_jsonl_rows(asset_bindings_path, AssetBinding)
    }
    source_map = {
        row.offer_id: row.source_id
        for row in load_jsonl_rows(offer_source_map_path, OfferSourceMap)
    }

    idx = GoldIndex(offers, labels, asset_map, bindings, source_map, taxonomy)

    recognition = _gen_recognition(idx, assets_dir)
    intent = _gen_intent(idx)
    retrieval = _gen_retrieval(idx)
    same_item = _gen_same_item(idx)
    ranking = _gen_ranking(idx, taxonomy)
    workflow = _gen_workflow(idx, assets_dir, dataset_id)
    retrieval_strategy: list[RetrievalStrategySample] = []
    if retrieval_strategy_path is not None:
        if not retrieval_strategy_path.is_file():
            raise ValueError(f"策略夹具文件不存在: {retrieval_strategy_path}")
        retrieval_strategy = [
            RetrievalStrategySample.model_validate(row)
            for row in load_jsonl_rows(retrieval_strategy_path, RetrievalStrategySample)
        ]
        if not retrieval_strategy:
            raise ValueError("策略夹具文件不能为空")

    datasets: dict[str, list[Any]] = {
        "recognition": recognition,
        "intent": intent,
        "retrieval": retrieval,
        "same_item": same_item,
        "ranking": ranking,
        "workflow": workflow,
    }
    if retrieval_strategy:
        datasets["retrieval_strategy"] = retrieval_strategy

    datasets_dir.mkdir(parents=True, exist_ok=True)
    counts_by_file: dict[str, int] = {}
    for kind, rows in datasets.items():
        filename = DATASET_FILENAMES[kind]
        rows_sorted = sorted(rows, key=lambda r: r.id)
        with (datasets_dir / filename).open("w", encoding="utf-8", newline="\n") as fh:
            for row in rows_sorted:
                fh.write(row.model_dump_json(exclude_none=True) + "\n")
        counts_by_file[filename] = len(rows_sorted)

    counts_by_split: dict[str, int] = defaultdict(int)
    for label in labels:
        counts_by_split[label.split] += 1
    counts_by_platform: dict[str, int] = defaultdict(int)
    categories: dict[str, int] = defaultdict(int)
    for o in offers:
        counts_by_platform[o.platform] += 1
        if o.category_id:
            categories[o.category_id] += 1

    manifest = build_manifest(
        dataset_id=dataset_id,
        dataset_version=dataset_version,
        taxonomy_version=taxonomy.taxonomy_version,
        created_at=created_at,
        as_of=as_of,
        categories=dict(categories),
        counts_by_file=counts_by_file,
        counts_by_split=dict(counts_by_split),
        counts_by_platform=dict(counts_by_platform),
        offer_count=len(offers),
        spu_count=len(idx.spu_offers),
        asset_count=len(asset_map),
        source_ids=_all_source_refs(datasets),
        known_limitations=[
            "数据集为确定性模拟生成器产出（用户授权，2026-08-21），非真实商品页采集；"
            "不满足计划 §5 真实来源要求；dataset_id 使用 sim 后缀如实标注。",
            "platform 覆盖 taobao/jd/pinduoduo 为模拟分配；本环境实测仅京东移动详情页"
            "可匿名访问，淘宝/拼多多需登录或验证码（计划 §5.2 禁止绕过）。",
            "label_source=agent（生成器按构造标注），无独立人工复核；gate_eligible=false。",
            "image_domain=listing_image：识别图片为 32x32 确定性模拟主图，不冒充用户实拍。",
            "recognition/intent/retrieval/workflow 指标在缺少真实模型配置时保持 pending；"
            "same_item/ranking 指标为领域代码确定性计算。",
            "live 运行需真实 Ark/Milvus/Checkpoint 配置（计划 §16 清单），本阶段不执行。",
        ],
        files={},
        image_domain="listing_image",
    )
    # README 先写，再计算全部提交文件的 SHA-256（manifest 自身不进入 files，§7.3）
    _write_readme(datasets_dir, dataset_id, manifest)
    final_manifest = manifest.model_copy(update={"files": compute_files_sha256(datasets_dir)})
    (datasets_dir / "manifest.json").write_text(
        final_manifest.model_dump_json(indent=2), encoding="utf-8"
    )
    return final_manifest


def _all_source_refs(datasets: dict[str, list[Any]]) -> list[str]:
    out: set[str] = set()
    for rows in datasets.values():
        for row in rows:
            meta = getattr(row, "meta", None)
            if meta is not None:
                out.update(meta.source_refs)
    return sorted(out)


def _write_readme(datasets_dir: Path, dataset_id: str, manifest: DatasetManifest) -> None:
    strategy_count = manifest.counts_by_file.get("retrieval_strategy_dataset.jsonl", 0)
    (datasets_dir / "README.md").write_text(
        f"""# {dataset_id}（provisional）

本目录由 `shijiajing-build-eval simulate → prepare → generate` 产出（Phase 1 方案）。
生成命令可通过 `--retrieval-strategy` 附带策略比较夹具；正式性能门禁必须提供该文件，
并在冻结前完成 `meta.label_source=adjudicated` 与完整 Offer→Gold SPU/SKU 映射校验。

## 来源声明（必须阅读）

- 本数据集为**确定性模拟数据**（用户授权，2026-08-21）：商品、价格、平台均为
  生成器构造，不是真实商品页采集；`sources.jsonl` 使用保留域名 example.com。
- `trust_level=provisional`、`label_method=agent_only`、`gate_eligible=false`：
  **不可作为发布门禁**。晋级 frozen 需满足计划 §16 条件。
- 识别图片为 32x32 模拟主图（`image_domain=listing_image`），不冒充用户实拍。

## 文件

| 文件 | 行数 | 说明 |
|---|---|---|
| manifest.json | - | 数据集清单（含文件 SHA-256） |
| offers_snapshot.jsonl | {manifest.offer_count} | 脱敏 Offer 快照 |
| offer_labels.jsonl | {manifest.offer_count} | Agent Gold 标签目录 |
| asset_inventory.jsonl | {manifest.asset_count} | 图片资产清单 |
| recognition_dataset.jsonl | {manifest.counts_by_file.get("recognition_dataset.jsonl", 0)} | 识别 |
| intent_dataset.jsonl | {manifest.counts_by_file.get("intent_dataset.jsonl", 0)} | 意图 |
| retrieval_dataset.jsonl | {manifest.counts_by_file.get("retrieval_dataset.jsonl", 0)} | 检索 |
| same_item_pairs.jsonl | {manifest.counts_by_file.get("same_item_pairs.jsonl", 0)} | 同款 |
| ranking_dataset.jsonl | {manifest.counts_by_file.get("ranking_dataset.jsonl", 0)} | 排序 |
| workflow_dataset.jsonl | {manifest.counts_by_file.get("workflow_dataset.jsonl", 0)} | 工作流 |
| retrieval_strategy_dataset.jsonl | {strategy_count} | 策略比较（可选） |

## 校验与评测

```powershell
uv run shijiajing-build-eval validate `
  --datasets-dir evals/datasets/provisional/v1 `
  --assets-dir evals/private/provisional_v1/raw/images
uv run shijiajing-eval --datasets-dir evals/datasets/provisional/v1 `
  --report-dir reports/provisional/v1 --no-gate
```
""",
        encoding="utf-8",
    )
