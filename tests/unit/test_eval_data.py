"""eval_data 契约与工具测试（Phase 1 §5–§7）。

- SourceSpec URL 公网校验（拒绝内网/回环/非 HTTP）。
- CaptureRecord 状态字面量；OfferGoldLabel 严格契约。
- stable_split 确定性 + 固定比例。
- HMAC 脱敏确定性与不泄漏原值。
- manifest files 不包含自身。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from shijiajing_agent.eval_data import (
    CaptureRecord,
    DatasetManifest,
    EvalAssetRef,
    EvalSampleMeta,
    GoldLabelDraft,
    HmacKeyStore,
    OfferGoldLabel,
    SourceSpec,
    compute_files_sha256,
    mask_id,
    stable_split,
)
from shijiajing_agent.eval_freeze import AdjudicationRecord


class TestSourceSpec:
    def test_valid_public_url_ok(self) -> None:
        source = SourceSpec(
            source_id="src:1",
            url="https://item.jd.com/100.html",
            platform="jd",
            category_id="headphone",
        )
        assert source.url == "https://item.jd.com/100.html"

    @pytest.mark.parametrize(
        "url",
        [
            "http://127.0.0.1:8000/item.html",
            "http://localhost/item.html",
            "http://192.168.1.10/item.html",
            "http://10.0.0.5/item.html",
            "file:///C:/tmp/item.html",
            "ftp://example.com/item.html",
            "http://172.16.0.1/item.html",
        ],
    )
    def test_private_or_bad_url_rejected(self, url: str) -> None:
        with pytest.raises(ValueError):
            SourceSpec(
                source_id="src:1",
                url=url,
                platform="jd",
                category_id="headphone",
            )

    def test_extra_field_forbidden(self) -> None:
        with pytest.raises(ValueError):
            SourceSpec.model_validate(
                {
                    "source_id": "src:1",
                    "url": "https://item.jd.com/100.html",
                    "platform": "jd",
                    "category_id": "headphone",
                    "unexpected": 1,
                }
            )


class TestCaptureAndLabels:
    def test_capture_status_literal(self) -> None:
        ok = CaptureRecord(capture_id="cap:1", source_id="src:1", status="ok")
        assert ok.status == "ok"
        with pytest.raises(ValueError):
            CaptureRecord(capture_id="cap:1", source_id="src:1", status="maybe")

    def test_gold_label_draft_requires_rationale(self) -> None:
        with pytest.raises(ValueError):
            GoldLabelDraft(
                source_id="src:1",
                gold_spu_id="gspu:1",
                gold_sku_id="gsku:1",
                label_rationale="",
            )

    def test_offer_gold_label_strict(self) -> None:
        label = OfferGoldLabel(
            offer_id="off:1",
            gold_spu_id="gspu:1",
            gold_sku_id="gsku:1",
            category_id="headphone",
            label_rationale="r",
            split="development",
        )
        assert label.label_source == "agent"
        with pytest.raises(ValueError):
            OfferGoldLabel(
                offer_id="off:1",
                gold_spu_id="gspu:1",
                gold_sku_id="gsku:1",
                category_id="headphone",
                label_rationale="r",
                split="dev",  # 非法 split
            )

    def test_eval_asset_ref_sha256_pattern(self) -> None:
        with pytest.raises(ValueError):
            EvalAssetRef(
                asset_id="ast:1",
                content_type="image/png",
                sha256="not-a-hash",
            )

    def test_eval_sample_meta_label_source(self) -> None:
        meta = EvalSampleMeta(
            dataset_version="1.0.0",
            split="holdout",
            category_id="headphone",
            label_source="agent",
        )
        assert meta.split == "holdout"
        with pytest.raises(ValueError):
            EvalSampleMeta(
                dataset_version="1.0.0",
                split="holdout",
                category_id="headphone",
                label_source="llm",  # 非法
            )


class TestStableSplit:
    def test_deterministic(self) -> None:
        assert stable_split("ds", "gspu:1") == stable_split("ds", "gspu:1")

    def test_dataset_id_changes_bucket(self) -> None:
        # 同一个 SPU 在不同 dataset_id 下可落入不同集合；同数据集内必须一致
        assert stable_split("a", "gspu:x") == stable_split("a", "gspu:x")

    def test_ratio_roughly_40_60(self) -> None:
        dev = sum(1 for i in range(2000) if stable_split("ds", f"gspu:{i}") == "development")
        ratio = dev / 2000
        assert 0.35 <= ratio <= 0.45


class TestHmacMasking:
    def test_mask_deterministic_and_hidden(self, tmp_path: Path) -> None:
        key_file = tmp_path / "keys" / "hmac.key"
        key = HmacKeyStore(key_file)
        masked = mask_id("off:", key, "jd|SIM100")
        assert masked.startswith("off:")
        assert "SIM100" not in masked
        assert mask_id("off:", key, "jd|SIM100") == masked
        # 不同输入 → 不同掩码
        assert mask_id("off:", key, "jd|SIM101") != masked

    def test_key_persisted(self, tmp_path: Path) -> None:
        key_file = tmp_path / "keys" / "hmac.key"
        a = HmacKeyStore(key_file)
        b = HmacKeyStore(key_file)
        assert a.mask("x") == b.mask("x")
        assert key_file.exists()


class TestManifest:
    def test_files_exclude_manifest(self, tmp_path: Path) -> None:
        (tmp_path / "a.jsonl").write_text("{}", encoding="utf-8")
        (tmp_path / "manifest.json").write_text("{}", encoding="utf-8")
        files = compute_files_sha256(tmp_path)
        assert set(files) == {"a.jsonl"}
        assert "manifest.json" not in files

    def test_manifest_contract(self) -> None:
        manifest = DatasetManifest(
            dataset_id="ds",
            dataset_schema_version="1.0",
            dataset_version="1.0.0",
            taxonomy_version="t",
            trust_level="provisional",
            label_method="agent_only",
            gate_eligible=False,
            created_at="2026-08-21T00:00:00+00:00",
            as_of="2026-08-21T00:00:00+00:00",
            categories={},
            counts_by_file={},
            counts_by_split={},
            counts_by_platform={},
            offer_count=0,
            spu_count=0,
            asset_count=0,
            files={},
        )
        assert manifest.trust_level == "provisional"
        with pytest.raises(ValueError):
            DatasetManifest(
                dataset_id="ds",
                dataset_schema_version="1.0",
                dataset_version="1.0.0",
                taxonomy_version="t",
                trust_level="not-a-level",
                label_method="agent_only",
                gate_eligible=False,
                created_at="x",
                as_of="x",
                categories={},
                counts_by_file={},
                counts_by_split={},
                counts_by_platform={},
                offer_count=0,
                spu_count=0,
                asset_count=0,
                files={},
            )


def test_adjudication_record_requires_distinct_reviewers() -> None:
    record = AdjudicationRecord(
        record_id="adj-1",
        dataset_id="dataset-1",
        dataset_version="1.0.0",
        decision="approved",
        review_scope="all_rows",
        adjudicator_ids=["human-a", "human-b"],
        reviewed_at="2026-08-22T00:00:00+00:00",
    )
    assert record.review_scope == "all_rows"
    with pytest.raises(ValueError):
        AdjudicationRecord.model_validate(
            record.model_dump(mode="json") | {"adjudicator_ids": ["human-a", "human-a"]}
        )
