"""把已完成独立人工仲裁的数据集安全晋级为 frozen。"""

from __future__ import annotations

import json
import shutil
import tempfile
import time
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from shijiajing_agent.eval_data import (
    DatasetManifest,
    OfferGoldLabel,
    compute_files_sha256,
    load_jsonl_rows,
    load_manifest,
)
from shijiajing_agent.evals import load_all_datasets

ADJUDICATION_RECORD_FILENAME = "adjudication_record.json"


class AdjudicationRecord(BaseModel):
    """人工仲裁完成证明；仅接受全量、双人独立仲裁记录。"""

    model_config = ConfigDict(extra="forbid")

    record_id: str = Field(min_length=1)
    dataset_id: str = Field(min_length=1)
    dataset_version: str = Field(min_length=1)
    decision: Literal["approved"]
    review_scope: Literal["all_rows"]
    adjudicator_ids: list[str] = Field(min_length=2)
    reviewed_at: str = Field(min_length=1)

    @model_validator(mode="after")
    def _distinct_adjudicators(self) -> AdjudicationRecord:
        if len(set(self.adjudicator_ids)) != len(self.adjudicator_ids):
            raise ValueError("adjudicator_ids 必须互不相同")
        return self


def load_adjudication_record(path: Path) -> AdjudicationRecord:
    try:
        return AdjudicationRecord.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"adjudication record 校验失败: {path}: {exc}") from exc


def write_adjudication_record(path: Path, record: AdjudicationRecord) -> None:
    path.write_text(
        json.dumps(record.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def validate_frozen_dataset_metadata(source_dir: Path, manifest: DatasetManifest) -> list[str]:
    """校验 frozen 产物携带的仲裁证明和全部文件摘要。"""
    errors: list[str] = []
    record_path = source_dir / ADJUDICATION_RECORD_FILENAME
    record: AdjudicationRecord | None = None
    if not record_path.is_file():
        errors.append(f"缺少 {ADJUDICATION_RECORD_FILENAME}")
    else:
        try:
            record = load_adjudication_record(record_path)
        except ValueError as exc:
            errors.append(str(exc))
    if record is not None:
        if record.dataset_id != manifest.dataset_id:
            errors.append("adjudication record dataset_id 与 manifest 不一致")
        if record.dataset_version != manifest.dataset_version:
            errors.append("adjudication record dataset_version 与 manifest 不一致")

    actual_files = compute_files_sha256(source_dir)
    for filename, expected_sha in manifest.files.items():
        if actual_files.get(filename) != expected_sha:
            errors.append(f"frozen 文件摘要不一致: {filename}")
    if len(actual_files) != len(manifest.files):
        errors.append("frozen manifest.files 与实际文件数量不一致")
    return errors


def _require_adjudicated_rows(source_dir: Path) -> None:
    labels = load_jsonl_rows(source_dir / "offer_labels.jsonl", OfferGoldLabel)
    non_adjudicated_labels = [
        label.offer_id for label in labels if label.label_source != "adjudicated"
    ]
    if non_adjudicated_labels:
        raise ValueError(f"offer_labels 仍包含非 adjudicated 标签: {non_adjudicated_labels[:5]}")

    datasets = load_all_datasets(source_dir)
    for kind, rows in datasets.items():
        for row in rows:
            meta = getattr(row, "meta", None)
            if meta is None or meta.label_source != "adjudicated":
                row_id = row.model_dump(mode="json").get("id", "<unknown>")
                raise ValueError(f"{kind} {row_id} 缺少 adjudicated meta.label_source")


def _commit_staging_dir(staging_dir: Path, output_dir: Path) -> None:
    """提交 staging 目录；Windows 文件扫描短暂占用目录时有限重试。"""
    delays = (0.05, 0.1, 0.2, 0.4)
    for _attempt, delay in enumerate((*delays, None)):
        try:
            staging_dir.replace(output_dir)
            return
        except PermissionError:
            if delay is None:
                raise
            time.sleep(delay)


def freeze_dataset(
    source_dir: Path, output_dir: Path, adjudication_record: AdjudicationRecord
) -> DatasetManifest:
    """复制并冻结数据集；不覆盖已有 output_dir，也不修改源目录。"""
    if not source_dir.is_dir():
        raise ValueError(f"源数据集目录不存在: {source_dir}")
    if output_dir.exists():
        raise ValueError(f"输出目录已存在，拒绝覆盖: {output_dir}")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest(source_dir)
    if manifest is None:
        raise ValueError("源数据集缺少 manifest.json")
    if (
        manifest.trust_level != "provisional"
        or manifest.label_method != "agent_only"
        or manifest.gate_eligible
    ):
        raise ValueError("只有 provisional/agent_only/gate_eligible=false 数据集可以冻结")
    if adjudication_record.dataset_id != manifest.dataset_id:
        raise ValueError("adjudication record dataset_id 与 manifest 不一致")
    if adjudication_record.dataset_version != manifest.dataset_version:
        raise ValueError("adjudication record dataset_version 与 manifest 不一致")

    _require_adjudicated_rows(source_dir)
    staging_dir = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=output_dir.parent))
    try:
        shutil.copytree(source_dir, staging_dir, dirs_exist_ok=True)
        write_adjudication_record(staging_dir / ADJUDICATION_RECORD_FILENAME, adjudication_record)
        frozen = manifest.model_copy(
            update={
                "trust_level": "frozen",
                "label_method": "adjudicated",
                "gate_eligible": True,
                "files": compute_files_sha256(staging_dir),
            }
        )
        (staging_dir / "manifest.json").write_text(
            json.dumps(frozen.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        _commit_staging_dir(staging_dir, output_dir)
        return frozen
    finally:
        if staging_dir.exists():
            shutil.rmtree(staging_dir)
