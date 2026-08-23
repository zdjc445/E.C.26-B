"""live 评测契约测试（Phase 1 §10、§13.2）。

- 六类 live runner 使用 Fake 端口全部写出正确 recorded。
- asset resolver 校验 SHA-256 后构建 data URL；摘要不符抛错。
- SameItemMatcher 生产节点与评测使用同一工厂与相同参数。
- run manifest 包含模型、Prompt、taxonomy 与 commit 标识。
- workflow 每次运行独立 session（run_id 前缀）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from shijiajing_agent.config import Settings
from shijiajing_agent.contracts import SkuGroup
from shijiajing_agent.domain.same_item import default_same_item_matcher
from shijiajing_agent.eval_data import (
    AssetMapEntry,
    OfferGoldLabel,
    asset_ref_to_image_ref,
    load_asset_map,
    sha256_hex,
)
from shijiajing_agent.eval_engineering import RetrievalStrategySample
from shijiajing_agent.evals import (
    EvalAssetRef,
    IntentSample,
    RankingSample,
    RecognitionExpected,
    RecognitionSample,
    RetrievalRecorded,
    RetrievalSample,
    SameItemSample,
    WorkflowSample,
)
from shijiajing_agent.evals_live import (
    CallCounts,
    live_intent,
    live_ranking,
    live_recognition,
    live_retrieval,
    live_retrieval_strategy,
    live_same_item,
    live_workflow,
    write_run_manifest,
)
from shijiajing_agent.ports.retrieval import RetrievalResult
from tests.workflow.conftest import (
    FakeExplanation,
    FakeRetrieval,
    candidate,
    make_deps,
    make_offer,
)


@pytest.fixture
def settings() -> Settings:
    return Settings()


@pytest.fixture
def assets_dir(tmp_path: Path) -> Path:
    images = tmp_path / "images"
    images.mkdir(parents=True)
    return images


def _write_asset(assets_dir: Path, asset_id: str, data: bytes) -> AssetMapEntry:
    path = assets_dir / f"{asset_id}.png"
    path.write_bytes(data)
    entry = AssetMapEntry(
        asset_id=asset_id,
        content_type="image/png",
        sha256=sha256_hex(data),
        width=16,
        height=16,
        local_path=f"{asset_id}.png",
        source_content_hash=sha256_hex(data),
    )
    entries = load_asset_map(assets_dir.parent / "asset_map.jsonl")
    entries[asset_id] = entry
    (assets_dir.parent / "asset_map.jsonl").write_text(
        "\n".join(e.model_dump_json() for e in entries.values()), encoding="utf-8"
    )
    return entry


def _tiny_png() -> bytes:
    from shijiajing_agent.eval_simulate import _make_png

    return _make_png(16, 16, b"contract-test")


@pytest.fixture
def gold_datasets_dir(tmp_path: Path) -> Path:
    """包含 offer_labels.jsonl 的迷你数据集目录（Gold catalog）。"""
    d = tmp_path / "datasets"
    d.mkdir()
    labels = [
        {
            "offer_id": "o-taobao",
            "gold_spu_id": "gspu:1",
            "gold_sku_id": "gsku:1",
            "category_id": "headphone",
            "identity_attributes": {"connectivity": "蓝牙", "wearing_style": "头戴式"},
            "variant_attributes": {"color": "黑色", "set_type": "单件"},
            "evidence_refs": ["sha256:" + "a" * 64],
            "label_source": "agent",
            "label_rationale": "test",
            "split": "development",
        },
        {
            "offer_id": "o-jd",
            "gold_spu_id": "gspu:1",
            "gold_sku_id": "gsku:1",
            "category_id": "headphone",
            "identity_attributes": {"connectivity": "蓝牙", "wearing_style": "头戴式"},
            "variant_attributes": {"color": "黑色", "set_type": "单件"},
            "evidence_refs": ["sha256:" + "b" * 64],
            "label_source": "agent",
            "label_rationale": "test",
            "split": "development",
        },
    ]
    (d / "offer_labels.jsonl").write_text(
        "\n".join(json.dumps(x, ensure_ascii=False) for x in labels), encoding="utf-8"
    )
    return d


class TestAssetResolver:
    def test_resolves_data_url_after_sha_check(self, assets_dir: Path) -> None:
        data = _tiny_png()
        entry = _write_asset(assets_dir, "ast-1", data)
        asset_map = load_asset_map(assets_dir.parent / "asset_map.jsonl")
        ref = EvalAssetRef(asset_id="ast-1", content_type="image/png", sha256=entry.sha256)
        image = asset_ref_to_image_ref(ref, assets_dir, asset_map)
        assert image.uri.startswith("data:image/png;base64,")
        assert image.image_id == "ast-1"

    def test_rejects_sha_mismatch(self, assets_dir: Path) -> None:
        data = _tiny_png()
        _write_asset(assets_dir, "ast-1", data)
        asset_map = load_asset_map(assets_dir.parent / "asset_map.jsonl")
        ref = EvalAssetRef(asset_id="ast-1", content_type="image/png", sha256="f" * 64)
        with pytest.raises(ValueError):
            asset_ref_to_image_ref(ref, assets_dir, asset_map)


class TestLiveRunners:
    @pytest.mark.asyncio
    async def test_live_recognition_writes_recorded(
        self, assets_dir: Path, taxonomy: object, settings: object
    ) -> None:
        deps, fakes = make_deps(taxonomy, settings)  # type: ignore[arg-type]
        data = _tiny_png()
        entry = _write_asset(assets_dir, "ast-1", data)
        sample = RecognitionSample(
            id="rec-1",
            asset=EvalAssetRef(asset_id="ast-1", content_type="image/png", sha256=entry.sha256),
            expected=RecognitionExpected(category_id="headphone"),
        )
        asset_map = load_asset_map(assets_dir.parent / "asset_map.jsonl")
        result = await live_recognition(sample, deps, assets_dir, asset_map)
        assert result.category_id == "headphone"
        assert fakes["vision"].calls == 1

    @pytest.mark.asyncio
    async def test_live_intent_replays_history(self, taxonomy: object, settings: object) -> None:
        deps, fakes = make_deps(taxonomy, settings)  # type: ignore[arg-type]
        sample = IntentSample(
            id="intent-1",
            text="预算1000以内",
            history=["我要买索尼耳机"],
            expected_patch={"max_price": 1000.0},
        )
        recorded = await live_intent(sample, deps)
        assert recorded.max_price == 1000.0
        assert recorded.conflict_detected is not None
        assert fakes["intent"].calls == 2  # 历史 1 轮 + 当前 1 轮

    @pytest.mark.asyncio
    async def test_live_retrieval_maps_to_gold(
        self, taxonomy: object, settings: object, gold_datasets_dir: Path
    ) -> None:
        deps, fakes = make_deps(taxonomy, settings)  # type: ignore[arg-type]
        result = RetrievalResult(
            candidates=[
                candidate("o-taobao", price=1899.0, platform="taobao"),
                candidate("o-jd", price=1999.0, platform="jd"),
            ],
            total_found=2,
        )
        fakes["retrieval"].sequence.append(result)  # type: ignore[attr-defined]
        from shijiajing_agent.evals_live import load_gold_catalog

        catalog = load_gold_catalog(gold_datasets_dir)
        sample = RetrievalSample(
            id="ret-1",
            query={"query_text": "索尼 WH-1000XM5", "hard_filters": {"category_id": "headphone"}},
            expected_spu_ids=["gspu:1"],
            expected_sku_ids=["gsku:1"],
        )
        recorded = await live_retrieval(sample, deps, catalog)
        assert isinstance(recorded, RetrievalRecorded)
        assert recorded.top_sku_ids == ["gsku:1"]
        assert recorded.spu_ids == ["gspu:1"]
        assert recorded.hard_filter_satisfied is True

    @pytest.mark.asyncio
    async def test_live_retrieval_strategy_refreshes_candidates_and_channels(
        self, taxonomy: object, settings: object
    ) -> None:
        deps, fakes = make_deps(taxonomy, settings)  # type: ignore[arg-type]
        fakes["retrieval"].sequence.append(
            RetrievalResult(
                candidates=[
                    candidate("offer-1", price=1899.0, platform="jd"),
                    candidate("offer-2", price=1999.0, platform="jd"),
                ],
                total_found=2,
            )
        )  # type: ignore[attr-defined]
        sample = RetrievalStrategySample(
            id="strategy-live-1",
            query={"query_text": "索尼耳机", "hard_filters": {"category_id": "headphone"}},
            candidates=[candidate("stale", price=1.0)],
            channel_orders={"dense": ["stale"]},
            expected_spu_ids=["gspu:1"],
            expected_sku_ids=["gsku:1"],
            expected_top_sku_ids=["gsku:1"],
        )

        catalog = {
            "offer-1": OfferGoldLabel(
                offer_id="offer-1",
                gold_spu_id="gold-spu-1",
                gold_sku_id="gold-sku-1",
                category_id="headphone",
                label_rationale="contract fixture",
                split="holdout",
            ),
            "offer-2": OfferGoldLabel(
                offer_id="offer-2",
                gold_spu_id="gold-spu-2",
                gold_sku_id="gold-sku-2",
                category_id="headphone",
                label_rationale="contract fixture",
                split="holdout",
            ),
        }
        refreshed = await live_retrieval_strategy(sample, deps, catalog)

        assert [c.offer.offer_id for c in refreshed.candidates] == ["offer-1", "offer-2"]
        assert refreshed.channel_orders["dense"] == ["offer-1", "offer-2"]
        assert refreshed.expected_sku_ids == ["gsku:1"]
        assert refreshed.gold_sku_by_offer_id == {
            "offer-1": "gold-sku-1",
            "offer-2": "gold-sku-2",
        }

    @pytest.mark.asyncio
    async def test_live_retrieval_rejects_missing_gold_catalog_mapping(
        self, taxonomy: object, settings: object
    ) -> None:
        deps, fakes = make_deps(taxonomy, settings)  # type: ignore[arg-type]
        unlabeled_result = RetrievalResult(
            candidates=[candidate("unlabeled-offer", price=1899.0, platform="jd")],
            total_found=1,
        )
        fakes["retrieval"].sequence.extend([unlabeled_result, unlabeled_result])  # type: ignore[attr-defined]
        sample = RetrievalStrategySample(
            id="strategy-missing-gold",
            query={"query_text": "索尼耳机", "hard_filters": {"category_id": "headphone"}},
            candidates=[candidate("stale", price=1.0)],
            channel_orders={"dense": ["stale"]},
            expected_spu_ids=["gold-spu-1"],
            expected_sku_ids=["gold-sku-1"],
            expected_top_sku_ids=["gold-sku-1"],
        )

        with pytest.raises(ValueError, match="Gold catalog 缺少 Offer 映射"):
            await live_retrieval_strategy(sample, deps, {})

        with pytest.raises(ValueError, match="Gold catalog 缺少 Offer 映射"):
            await live_retrieval(
                RetrievalSample(
                    id="retrieval-missing-gold",
                    query={
                        "query_text": "索尼耳机",
                        "hard_filters": {"category_id": "headphone"},
                    },
                ),
                deps,
                {},
            )

    @pytest.mark.asyncio
    async def test_live_same_item_uses_production_factory(
        self, taxonomy: object, settings: object
    ) -> None:
        deps, _ = make_deps(taxonomy, settings)  # type: ignore[arg-type]
        a = make_offer("o-1", price=1899.0, platform="taobao")
        b = make_offer("o-2", price=1999.0, platform="jd")
        sample = SameItemSample(
            id="si-1",
            offer_a=a.model_dump(exclude_none=True),
            offer_b=b.model_dump(exclude_none=True),
            same_spu=True,
            same_sku=True,
        )
        recorded = await live_same_item(sample, deps)
        assert recorded.verdict == "same"
        # 与生产节点同一工厂：阈值一致
        matcher = default_same_item_matcher(deps.taxonomy)
        assert matcher._accept == 0.82
        assert matcher._review == 0.68

    @pytest.mark.asyncio
    async def test_live_ranking_saves_real_explanation(
        self, taxonomy: object, settings: object
    ) -> None:
        deps, _ = make_deps(taxonomy, settings, explanation=FakeExplanation())  # type: ignore[arg-type]
        o1 = make_offer("o-1", price=1899.0, platform="taobao")
        o2 = make_offer("o-2", price=1999.0, platform="jd")
        group = SkuGroup(
            group_id="g:1",
            spu_id="spu:1",
            offers=[o1, o2],
            min_price=1899.0,
            max_price=1999.0,
            average_price=1949.0,
            min_price_offer_id="o-1",
            offer_count=2,
            platform_count=2,
            match_confidence=0.9,
            category_id="headphone",
            brand="Sony",
            model="WH-1000XM5",
            title=o1.title,
        )
        sample = RankingSample(
            id="rank-1",
            query={
                "text": "索尼 WH-1000XM5 比价",
                "sort_by": "price_asc",
                "preferences": ["lowest_price"],
                "hard_filters": {"category_id": "headphone"},
            },
            groups=[group.model_dump(exclude_none=True)],
            preferred_order=["g:1"],
        )
        recorded = await live_ranking(sample, deps, CallCounts())
        assert recorded.ranked_group_ids == ["g:1"]
        assert recorded.explanation is not None
        assert recorded.explanation_verified is True

    @pytest.mark.asyncio
    async def test_live_workflow_writes_full_recorded(
        self,
        taxonomy: object,
        settings: object,
        gold_datasets_dir: Path,
    ) -> None:
        deps, fakes = make_deps(
            taxonomy,
            settings,  # type: ignore[arg-type]
            retrieval=FakeRetrieval(),
        )
        result = RetrievalResult(
            candidates=[
                candidate("o-taobao", price=1899.0, platform="taobao"),
                candidate("o-jd", price=1999.0, platform="jd"),
            ],
            total_found=2,
        )
        fakes["retrieval"].sequence.append(result)  # type: ignore[attr-defined]
        from shijiajing_agent.evals_live import load_gold_catalog

        catalog = load_gold_catalog(gold_datasets_dir)
        sample = WorkflowSample(
            id="wf-1",
            turns=[
                {
                    "session_id": "wf-1",
                    "request_id": "wf-1-t0",
                    "text": "索尼 WH-1000XM5 耳机",
                }
            ],
            expected_status="success",
            expected_sku_ids=["gsku:1"],
            expected_final_constraints={
                "category_id": "headphone",
                "brand": "Sony",
                "model": "WH-1000XM5",
            },
        )
        recorded = await live_workflow(sample, deps, catalog, run_id="run:test")
        assert recorded.status is not None
        assert recorded.latency_ms is not None and len(recorded.latency_ms) == 1
        assert recorded.model_calls_per_turn is not None
        assert "gsku:1" in recorded.sku_ids
        assert recorded.state_exact is not None


class TestRunManifest:
    def test_manifest_contains_models_taxonomy_commit(
        self, tmp_path: Path, taxonomy: object, settings: object
    ) -> None:
        from shijiajing_agent.config import Settings

        s = Settings(ark_vision_model="v1", ark_text_model="t1", milvus_collection="coll")
        path = write_run_manifest(
            tmp_path,
            dataset_id="ds-test",
            settings=s,
            taxonomy=taxonomy,  # type: ignore[arg-type]
            generated_at="2026-08-21T00:00:00+00:00",
            run_id="run:abc",
            repo_root=Path(__file__).resolve().parents[2],
        )
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["models"]["vision"] == "v1"
        assert data["taxonomy_version"] == taxonomy.taxonomy_version  # type: ignore[attr-defined]
        assert data["code_commit"]  # 非空（仓库内或 unknown）
        assert data["params"]["same_item_accept_threshold"] == 0.82
        assert data["index"]["type"] == "milvus"
