"""shijiajing-build-eval CLI 测试（Phase 1 §5–§9）。

- simulate → prepare → generate → validate 全链路（固定规模，确定性）。
- prepare 重复运行字节一致（§6.1）。
- validate 缺失目录 / 数据损坏 → 非零退出。
- index dry-run 不需要外部配置。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from shijiajing_agent import eval_freeze
from shijiajing_agent.eval_data import DATASET_ID_SIM, DatasetManifest, compute_files_sha256
from shijiajing_agent.eval_engineering import RetrievalStrategySample
from shijiajing_agent.eval_freeze import AdjudicationRecord
from shijiajing_agent.evals import default_datasets_dir
from shijiajing_agent.tools.build_eval import main as build_eval_main

_AS_OF = "2026-08-21T00:00:00+00:00"


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    return tmp_path / "workspace"


@pytest.fixture
def datasets_dir(tmp_path: Path) -> Path:
    return tmp_path / "datasets"


def _run_pipeline(workspace: Path, datasets_dir: Path) -> None:
    assert build_eval_main(["simulate", "--workspace", str(workspace), "--as-of", _AS_OF]) == 0
    assert (
        build_eval_main(
            [
                "prepare",
                "--workspace",
                str(workspace),
                "--out",
                str(datasets_dir),
                "--as-of",
                _AS_OF,
            ]
        )
        == 0
    )
    assert (
        build_eval_main(
            [
                "generate",
                "--snapshot",
                str(datasets_dir / "offers_snapshot.jsonl"),
                "--labels",
                str(datasets_dir / "offer_labels.jsonl"),
                "--assets",
                str(datasets_dir / "asset_inventory.jsonl"),
                "--asset-map",
                str(workspace / "asset_map.jsonl"),
                "--asset-bindings",
                str(workspace / "asset_bindings.jsonl"),
                "--offer-source-map",
                str(workspace / "offer_source_map.jsonl"),
                "--assets-dir",
                str(workspace / "raw" / "images"),
                "--out",
                str(datasets_dir),
                "--as-of",
                _AS_OF,
            ]
        )
        == 0
    )


def test_full_pipeline_round_trip(workspace: Path, datasets_dir: Path) -> None:
    """全链路：simulate → prepare → generate → validate 全部退出 0，计数符合 §4。"""
    _run_pipeline(workspace, datasets_dir)
    assert (
        build_eval_main(
            [
                "validate",
                "--datasets-dir",
                str(datasets_dir),
                "--assets-dir",
                str(workspace / "raw" / "images"),
                "--workspace",
                str(workspace),
            ]
        )
        == 0
    )

    manifest = json.loads((datasets_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["dataset_id"] == DATASET_ID_SIM
    assert manifest["trust_level"] == "provisional"
    assert manifest["gate_eligible"] is False
    assert manifest["offer_count"] == 1000
    assert manifest["spu_count"] == 200
    assert manifest["asset_count"] == 300
    assert manifest["counts_by_file"]["recognition_dataset.jsonl"] == 300
    assert manifest["counts_by_file"]["intent_dataset.jsonl"] == 300
    assert manifest["counts_by_file"]["retrieval_dataset.jsonl"] == 150
    assert manifest["counts_by_file"]["same_item_pairs.jsonl"] == 600
    assert manifest["counts_by_file"]["ranking_dataset.jsonl"] == 90
    assert manifest["counts_by_file"]["workflow_dataset.jsonl"] == 120
    assert manifest["image_domain"] == "listing_image"
    assert any("模拟" in limitation for limitation in manifest["known_limitations"])
    # manifest 自身不进入 files
    assert "manifest.json" not in manifest["files"]
    assert "README.md" in manifest["files"]


def test_generate_copies_optional_retrieval_strategy_fixture(
    workspace: Path, datasets_dir: Path
) -> None:
    _run_pipeline(workspace, datasets_dir)
    strategy_source = default_datasets_dir() / "retrieval_strategy_dataset.jsonl"
    output_dir = datasets_dir.parent / "with-strategy"

    assert (
        build_eval_main(
            [
                "generate",
                "--snapshot",
                str(datasets_dir / "offers_snapshot.jsonl"),
                "--labels",
                str(datasets_dir / "offer_labels.jsonl"),
                "--assets",
                str(datasets_dir / "asset_inventory.jsonl"),
                "--asset-map",
                str(workspace / "asset_map.jsonl"),
                "--asset-bindings",
                str(workspace / "asset_bindings.jsonl"),
                "--offer-source-map",
                str(workspace / "offer_source_map.jsonl"),
                "--assets-dir",
                str(workspace / "raw" / "images"),
                "--retrieval-strategy",
                str(strategy_source),
                "--out",
                str(output_dir),
                "--as-of",
                _AS_OF,
            ]
        )
        == 0
    )

    source_rows = [
        json.loads(line)
        for line in strategy_source.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    generated_rows = [
        json.loads(line)
        for line in (output_dir / "retrieval_strategy_dataset.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    normalized_source = [
        RetrievalStrategySample.model_validate(row).model_dump(mode="json", exclude_none=True)
        for row in source_rows
    ]
    normalized_generated = [
        RetrievalStrategySample.model_validate(row).model_dump(mode="json", exclude_none=True)
        for row in generated_rows
    ]
    assert normalized_generated == sorted(normalized_source, key=lambda row: row["id"])
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["counts_by_file"]["retrieval_strategy_dataset.jsonl"] == len(source_rows)


def test_prepare_deterministic_bytes(workspace: Path, datasets_dir: Path) -> None:
    """§6.1：相同输入 + 相同密钥 + 相同 as-of → 输出字节一致（按 id 排序）。"""
    _run_pipeline(workspace, datasets_dir)
    out2 = datasets_dir.parent / "datasets2"
    assert (
        build_eval_main(
            [
                "prepare",
                "--workspace",
                str(workspace),
                "--out",
                str(out2),
                "--as-of",
                _AS_OF,
            ]
        )
        == 0
    )
    for name in ("offers_snapshot.jsonl", "offer_labels.jsonl", "asset_inventory.jsonl"):
        a = (datasets_dir / name).read_bytes()
        b = (out2 / name).read_bytes()
        assert a == b, f"{name} 输出不一致"


def test_simulate_is_deterministic(workspace: Path, tmp_path: Path) -> None:
    """相同 dataset_id + as-of → sources.jsonl 字节一致。"""
    _run_pipeline(workspace, tmp_path / "d1")
    workspace2 = tmp_path / "workspace2"
    assert build_eval_main(["simulate", "--workspace", str(workspace2), "--as-of", _AS_OF]) == 0
    assert (workspace / "sources.jsonl").read_bytes() == (workspace2 / "sources.jsonl").read_bytes()


def test_validate_missing_datasets_dir_exits_2(tmp_path: Path) -> None:
    code = build_eval_main(["validate", "--datasets-dir", str(tmp_path / "no-such-dir")])
    assert code == 2


def test_validate_corrupt_data_exits_1(workspace: Path, datasets_dir: Path) -> None:
    _run_pipeline(workspace, datasets_dir)
    # 破坏一行 same_item 标签 → 校验必须失败
    pairs = datasets_dir / "same_item_pairs.jsonl"
    lines = pairs.read_text(encoding="utf-8").splitlines()
    row = json.loads(lines[0])
    row["same_sku"] = True
    row["same_spu"] = False  # same_sku 但 same_spu=false → 矛盾
    lines[0] = json.dumps(row, ensure_ascii=False)
    pairs.write_text("\n".join(lines), encoding="utf-8")
    code = build_eval_main(
        [
            "validate",
            "--datasets-dir",
            str(datasets_dir),
            "--assets-dir",
            str(workspace / "raw" / "images"),
            "--workspace",
            str(workspace),
        ]
    )
    assert code == 1


def test_generate_requires_inputs(tmp_path: Path) -> None:
    code = build_eval_main(
        [
            "generate",
            "--snapshot",
            str(tmp_path / "missing.jsonl"),
            "--labels",
            str(tmp_path / "missing.jsonl"),
            "--assets",
            str(tmp_path / "missing.jsonl"),
            "--asset-map",
            str(tmp_path / "missing.jsonl"),
            "--asset-bindings",
            str(tmp_path / "missing.jsonl"),
            "--offer-source-map",
            str(tmp_path / "missing.jsonl"),
            "--assets-dir",
            str(tmp_path / "img"),
            "--out",
            str(tmp_path / "out"),
            "--as-of",
            _AS_OF,
        ]
    )
    assert code == 2


def test_freeze_requires_adjudicated_rows_and_writes_frozen_manifest(
    workspace: Path, datasets_dir: Path, tmp_path: Path
) -> None:
    _run_pipeline(workspace, datasets_dir)

    manifest = json.loads((datasets_dir / "manifest.json").read_text(encoding="utf-8"))
    record_path = tmp_path / "adjudication.json"
    record_path.write_text(
        json.dumps(
            {
                "record_id": "adj-1",
                "dataset_id": manifest["dataset_id"],
                "dataset_version": manifest["dataset_version"],
                "decision": "approved",
                "review_scope": "all_rows",
                "adjudicator_ids": ["human-a", "human-b"],
                "reviewed_at": "2026-08-22T00:00:00+00:00",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    rejected_dir = tmp_path / "rejected"
    assert (
        build_eval_main(
            [
                "freeze",
                "--datasets-dir",
                str(datasets_dir),
                "--out",
                str(rejected_dir),
                "--adjudication-record",
                str(record_path),
                "--assets-dir",
                str(workspace / "raw" / "images"),
                "--workspace",
                str(workspace),
            ]
        )
        == 2
    )
    assert not rejected_dir.exists()

    for path in datasets_dir.glob("*.jsonl"):
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        for row in rows:
            if isinstance(row.get("meta"), dict):
                assert row["meta"]["label_source"] == "agent"
                row["meta"]["label_source"] = "adjudicated"
        path.write_text(
            "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
            encoding="utf-8",
        )

    labels_path = datasets_dir / "offer_labels.jsonl"
    labels = [json.loads(line) for line in labels_path.read_text(encoding="utf-8").splitlines()]
    for label in labels:
        label["label_source"] = "adjudicated"
        label["label_rationale"] = "independent adjudication record adj-1"
    labels_path.write_text(
        "\n".join(json.dumps(label, ensure_ascii=False) for label in labels) + "\n",
        encoding="utf-8",
    )

    manifest_path = datasets_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"] = compute_files_sha256(datasets_dir)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    frozen_dir = tmp_path / "frozen"
    assert (
        build_eval_main(
            [
                "freeze",
                "--datasets-dir",
                str(datasets_dir),
                "--out",
                str(frozen_dir),
                "--adjudication-record",
                str(record_path),
                "--assets-dir",
                str(workspace / "raw" / "images"),
                "--workspace",
                str(workspace),
            ]
        )
        == 0
    )
    frozen_manifest = json.loads((frozen_dir / "manifest.json").read_text(encoding="utf-8"))
    assert frozen_manifest["trust_level"] == "frozen"
    assert frozen_manifest["label_method"] == "adjudicated"
    assert frozen_manifest["gate_eligible"] is True
    assert (frozen_dir / "adjudication_record.json").exists()
    assert (
        build_eval_main(
            [
                "validate",
                "--datasets-dir",
                str(frozen_dir),
                "--assets-dir",
                str(workspace / "raw" / "images"),
                "--workspace",
                str(workspace),
            ]
        )
        == 0
    )


def test_freeze_cleans_staging_directory_when_write_fails(tmp_path: Path, monkeypatch) -> None:
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "payload.txt").write_text("payload", encoding="utf-8")
    manifest = DatasetManifest(
        dataset_id="dataset-1",
        dataset_schema_version="1.0",
        dataset_version="1.0.0",
        taxonomy_version="taxonomy-1",
        trust_level="provisional",
        label_method="agent_only",
        gate_eligible=False,
        created_at="2026-08-22T00:00:00+00:00",
        as_of="2026-08-22T00:00:00+00:00",
        categories={},
        counts_by_file={},
        counts_by_split={},
        counts_by_platform={},
        offer_count=0,
        spu_count=0,
        asset_count=0,
        files={},
    )
    manifest = manifest.model_copy(update={"files": compute_files_sha256(source_dir)})
    (source_dir / "manifest.json").write_text(
        json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False), encoding="utf-8"
    )
    record = AdjudicationRecord(
        record_id="adj-1",
        dataset_id="dataset-1",
        dataset_version="1.0.0",
        decision="approved",
        review_scope="all_rows",
        adjudicator_ids=["human-a", "human-b"],
        reviewed_at="2026-08-22T00:00:00+00:00",
    )
    monkeypatch.setattr(eval_freeze, "_require_adjudicated_rows", lambda _: None)

    def fail_write(*args, **kwargs):
        raise OSError("simulated record write failure")

    monkeypatch.setattr(eval_freeze, "write_adjudication_record", fail_write)
    with pytest.raises(OSError, match="simulated record write failure"):
        eval_freeze.freeze_dataset(source_dir, tmp_path / "frozen", record)
    assert not (tmp_path / "frozen").exists()
    assert list(tmp_path.glob(".frozen.*")) == []


def test_index_dry_run_without_external_config(
    workspace: Path, datasets_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§12：dry-run 在无外部配置环境可运行。"""
    _run_pipeline(workspace, datasets_dir)
    # 清空全部外部配置环境变量
    for key in list(os.environ):
        if key.startswith("SHIJIAJING_") and key not in ("SHIJIAJING_ENV",):
            monkeypatch.delenv(key, raising=False)
    from shijiajing_agent.tools.index_products import main as index_main

    code = index_main([str(datasets_dir / "offers_snapshot.jsonl"), "--dry-run"])
    assert code == 0
