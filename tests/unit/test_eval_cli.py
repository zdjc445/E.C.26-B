"""评测 CLI（shijiajing-eval）测试（§24 阶段 6 离线评测脚本 + Phase 1 §11 门禁语义）。

- 种子数据（无 manifest）视为 provisional：默认退出码 1；``--no-gate`` 退出 0；
  ``--frozen`` 返回配置错误 2 且不写 frozen report；
- frozen manifest 数据：门禁通过时 ``--frozen`` 写入 frozen_eval_report.md；
- 数据集目录缺失 / 为空 → 退出码 2；
- 存在阻断指标不达标的数据 → 退出码 1 且输出失败明细；
- ``--output-datasets-dir`` 与 ``--freeze-dir`` 同时出现 → 退出码 2。
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from shijiajing_agent.eval_data import compute_files_sha256
from shijiajing_agent.evals import default_datasets_dir
from shijiajing_agent.tools import run_eval as run_eval_module
from shijiajing_agent.tools.run_eval import main as eval_main

_PASS = 0
_CONFIG_ERROR = 2
_GATE_FAIL = 1


@pytest.fixture
def seed_dir() -> Path:
    return default_datasets_dir()


@pytest.fixture
def report_dir(tmp_path: Path) -> Path:
    return tmp_path / "reports"


def test_offline_run_seed_datasets_no_gate_passes(
    seed_dir: Path, report_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """§11：provisional 数据配合 --no-gate 成功生成报告返回 0。"""
    code = eval_main(
        ["--datasets-dir", str(seed_dir), "--report-dir", str(report_dir), "--no-gate"]
    )
    assert code == _PASS
    assert "阻断指标全部达标" in capsys.readouterr().out
    json_report = json.loads((report_dir / "eval_report.json").read_text(encoding="utf-8"))
    assert json_report["gate"] is True
    assert json_report["trust_level"] == "provisional"
    assert json_report["release_gate_eligible"] is False
    assert (report_dir / "eval_report.md").exists()
    assert (report_dir / "engineering_eval_report.md").exists()
    assert (report_dir / "retrieval_strategy_comparison.md").exists()
    engineering_report = json.loads(
        (report_dir / "engineering_eval_report.json").read_text(encoding="utf-8")
    )
    assert engineering_report["invariant_gate_passed"] is True
    assert all(
        item["sample_count"] > 0 and item["violation_count"] == 0
        for item in engineering_report["invariants"]
    )


def test_offline_run_removes_stale_optional_strategy_report(
    seed_dir: Path, tmp_path: Path, report_dir: Path
) -> None:
    reduced_dir = tmp_path / "reduced-datasets"
    shutil.copytree(seed_dir, reduced_dir)
    (reduced_dir / "retrieval_strategy_dataset.jsonl").unlink()
    report_dir.mkdir()
    for filename in (
        "retrieval_strategy_comparison.json",
        "retrieval_strategy_comparison.md",
    ):
        (report_dir / filename).write_text("stale", encoding="utf-8")

    code = eval_main(
        ["--datasets-dir", str(reduced_dir), "--report-dir", str(report_dir), "--no-gate"]
    )

    assert code == _PASS
    assert not (report_dir / "retrieval_strategy_comparison.json").exists()
    assert not (report_dir / "retrieval_strategy_comparison.md").exists()


def test_report_staging_failure_cleans_staging_and_keeps_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report_dir = tmp_path / "reports"
    report_dir.mkdir()
    target = report_dir / "eval_report.md"
    target.write_text("existing", encoding="utf-8")
    original_write_text = Path.write_text

    def fail_staging_write(
        self: Path,
        data: str,
        encoding: str | None = None,
        errors: str | None = None,
        newline: str | None = None,
    ) -> int:
        if self.parent.name.startswith(".eval-report."):
            raise OSError("simulated report staging failure")
        return original_write_text(self, data, encoding=encoding, errors=errors, newline=newline)

    monkeypatch.setattr(Path, "write_text", fail_staging_write)
    with pytest.raises(ValueError, match="评测报告 staging 提交失败"):
        run_eval_module._commit_report_artifacts(
            report_dir, {"eval_report.md": "new", "eval_report.json": "{}"}
        )

    assert target.read_text(encoding="utf-8") == "existing"
    assert not list(report_dir.glob(".eval-report.*"))


def test_report_commit_failure_returns_config_error_without_old_artifacts(
    seed_dir: Path, report_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report_dir.mkdir()
    for filename in (
        "eval_report.json",
        "eval_report.md",
        "engineering_eval_report.json",
        "engineering_eval_report.md",
    ):
        (report_dir / filename).write_text("stale", encoding="utf-8")

    def fail_commit(_: Path, __: dict[str, str]) -> None:
        raise ValueError("simulated report commit failure")

    monkeypatch.setattr(run_eval_module, "_commit_report_artifacts", fail_commit)
    code = eval_main(
        ["--datasets-dir", str(seed_dir), "--report-dir", str(report_dir), "--no-gate"]
    )

    assert code == _CONFIG_ERROR
    assert not list(report_dir.glob("eval_report.*"))
    assert not list(report_dir.glob("engineering_eval_report.*"))


def test_seed_default_exit_1_provisional(seed_dir: Path, report_dir: Path) -> None:
    """§11：provisional 数据默认 CLI 退出码为 1（不可作为发布门禁）。"""
    code = eval_main(["--datasets-dir", str(seed_dir), "--report-dir", str(report_dir)])
    assert code == _GATE_FAIL
    assert not (report_dir / "frozen_eval_report.md").exists()


def test_frozen_flag_on_provisional_exits_2(
    seed_dir: Path, report_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """§11：provisional 使用 --frozen 返回配置错误码 2，不写 frozen report。"""
    report_dir.mkdir()
    (report_dir / "frozen_eval_report.md").write_text("stale", encoding="utf-8")
    code = eval_main(["--datasets-dir", str(seed_dir), "--report-dir", str(report_dir), "--frozen"])
    assert code == _CONFIG_ERROR
    assert "manifest.json" in capsys.readouterr().err
    assert not (report_dir / "frozen_eval_report.md").exists()


def _write_frozen_manifest(datasets_dir: Path) -> None:
    """把数据集目录标记为 frozen + adjudicated（gate_eligible=true）。"""
    adjudication = {
        "record_id": "adj-test-1",
        "dataset_id": "shijiajing-test-frozen",
        "dataset_version": "1.0.0",
        "decision": "approved",
        "review_scope": "all_rows",
        "adjudicator_ids": ["human-a", "human-b"],
        "reviewed_at": "2026-08-22T00:00:00+00:00",
    }
    (datasets_dir / "adjudication_record.json").write_text(
        json.dumps(adjudication, ensure_ascii=False), encoding="utf-8"
    )
    manifest = {
        "dataset_id": "shijiajing-test-frozen",
        "dataset_schema_version": "1.0",
        "dataset_version": "1.0.0",
        "taxonomy_version": "test",
        "trust_level": "frozen",
        "label_method": "adjudicated",
        "gate_eligible": True,
        "created_at": "2026-08-21T00:00:00+00:00",
        "as_of": "2026-08-21T00:00:00+00:00",
        "categories": {},
        "counts_by_file": {},
        "counts_by_split": {},
        "counts_by_platform": {},
        "offer_count": 0,
        "spu_count": 0,
        "asset_count": 0,
        "files": compute_files_sha256(datasets_dir),
        "known_limitations": [],
    }
    (datasets_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
    )


def test_frozen_flag_writes_frozen_report_when_eligible(
    seed_dir: Path, tmp_path: Path, report_dir: Path
) -> None:
    """frozen + adjudicated 数据：门禁通过时 --frozen 写入 frozen report 并退出 0。"""
    frozen_dir = tmp_path / "frozen"
    shutil.copytree(seed_dir, frozen_dir)
    _write_frozen_manifest(frozen_dir)
    code = eval_main(
        ["--datasets-dir", str(frozen_dir), "--report-dir", str(report_dir), "--frozen"]
    )
    assert code == _PASS
    frozen = report_dir / "frozen_eval_report.md"
    assert frozen.exists()
    assert "阻断指标全部达标" in frozen.read_text(encoding="utf-8")


def test_frozen_flag_rejects_non_adjudicated_manifest(
    seed_dir: Path, tmp_path: Path, report_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    frozen_dir = tmp_path / "frozen"
    shutil.copytree(seed_dir, frozen_dir)
    _write_frozen_manifest(frozen_dir)
    manifest_path = frozen_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["label_method"] = "human"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

    code = eval_main(
        ["--datasets-dir", str(frozen_dir), "--report-dir", str(report_dir), "--frozen"]
    )
    assert code == _CONFIG_ERROR
    assert "label_method=adjudicated" in capsys.readouterr().err
    assert not (report_dir / "frozen_eval_report.md").exists()


def test_frozen_flag_requires_adjudication_record(
    seed_dir: Path, tmp_path: Path, report_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    frozen_dir = tmp_path / "frozen"
    shutil.copytree(seed_dir, frozen_dir)
    _write_frozen_manifest(frozen_dir)
    (frozen_dir / "adjudication_record.json").unlink()

    code = eval_main(
        ["--datasets-dir", str(frozen_dir), "--report-dir", str(report_dir), "--frozen"]
    )
    assert code == _CONFIG_ERROR
    assert "adjudication_record.json" in capsys.readouterr().err
    assert not (report_dir / "frozen_eval_report.md").exists()


def test_frozen_flag_rejects_tampered_dataset_file(
    seed_dir: Path, tmp_path: Path, report_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    frozen_dir = tmp_path / "frozen"
    shutil.copytree(seed_dir, frozen_dir)
    _write_frozen_manifest(frozen_dir)
    dataset_path = frozen_dir / "recognition_dataset.jsonl"
    dataset_path.write_text(dataset_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    code = eval_main(
        ["--datasets-dir", str(frozen_dir), "--report-dir", str(report_dir), "--frozen"]
    )
    assert code == _CONFIG_ERROR
    assert "文件摘要不一致" in capsys.readouterr().err
    assert not (report_dir / "frozen_eval_report.md").exists()


def test_frozen_flag_does_not_write_report_when_metric_gate_fails(
    seed_dir: Path, tmp_path: Path, report_dir: Path
) -> None:
    frozen_dir = tmp_path / "frozen"
    _corrupt_pairs_dir(seed_dir, frozen_dir)
    _write_frozen_manifest(frozen_dir)
    report_dir.mkdir()
    (report_dir / "frozen_eval_report.md").write_text("stale", encoding="utf-8")

    code = eval_main(
        ["--datasets-dir", str(frozen_dir), "--report-dir", str(report_dir), "--frozen"]
    )
    assert code == _GATE_FAIL
    assert not (report_dir / "frozen_eval_report.md").exists()


def test_frozen_report_write_failure_leaves_no_report_or_staging_file(
    seed_dir: Path,
    tmp_path: Path,
    report_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    frozen_dir = tmp_path / "frozen"
    shutil.copytree(seed_dir, frozen_dir)
    _write_frozen_manifest(frozen_dir)
    report_dir.mkdir()
    (report_dir / "frozen_eval_report.md").write_text("stale", encoding="utf-8")

    def fail_mkstemp(**_: object) -> tuple[int, str]:
        raise OSError("simulated report write failure")

    monkeypatch.setattr(run_eval_module.tempfile, "mkstemp", fail_mkstemp)
    code = eval_main(
        ["--datasets-dir", str(frozen_dir), "--report-dir", str(report_dir), "--frozen"]
    )

    assert code == _CONFIG_ERROR
    assert "冻结报告写入失败" in capsys.readouterr().err
    assert not (report_dir / "frozen_eval_report.md").exists()
    assert not list(report_dir.glob(".frozen_eval_report.md.*.tmp"))


def test_missing_datasets_dir_exits_2(tmp_path: Path, report_dir: Path) -> None:
    code = eval_main(
        ["--datasets-dir", str(tmp_path / "no-such-dir"), "--report-dir", str(report_dir)]
    )
    assert code == _CONFIG_ERROR


def test_empty_datasets_dir_exits_2(tmp_path: Path, report_dir: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    code = eval_main(["--datasets-dir", str(empty), "--report-dir", str(report_dir)])
    assert code == _CONFIG_ERROR


def test_both_output_args_exit_2(seed_dir: Path, tmp_path: Path, report_dir: Path) -> None:
    """§10：两个输出参数同时出现时返回配置错误 2。"""
    code = eval_main(
        [
            "--datasets-dir",
            str(seed_dir),
            "--report-dir",
            str(report_dir),
            "--output-datasets-dir",
            str(tmp_path / "out"),
            "--freeze-dir",
            str(tmp_path / "out2"),
        ]
    )
    assert code == _CONFIG_ERROR


def test_live_output_refuses_existing_directory(
    seed_dir: Path, tmp_path: Path, report_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output_dir = tmp_path / "live-output"
    output_dir.mkdir()
    marker = output_dir / "marker.txt"
    marker.write_text("keep", encoding="utf-8")

    code = eval_main(
        [
            "--datasets-dir",
            str(seed_dir),
            "--report-dir",
            str(report_dir),
            "--live",
            "--output-datasets-dir",
            str(output_dir),
        ]
    )
    assert code == _CONFIG_ERROR
    assert "拒绝覆盖" in capsys.readouterr().err
    assert marker.read_text(encoding="utf-8") == "keep"


def test_live_execution_failure_returns_config_error(
    seed_dir: Path, report_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    async def fail_live(*args, **kwargs):
        raise RuntimeError("simulated live adapter failure")

    monkeypatch.setattr(run_eval_module, "_run_live", fail_live)
    code = eval_main(["--datasets-dir", str(seed_dir), "--report-dir", str(report_dir), "--live"])

    assert code == _CONFIG_ERROR
    error = capsys.readouterr().err
    assert "live 评测执行失败" in error
    assert "simulated live adapter failure" in error


def test_live_output_staging_is_removed_when_serialization_fails(tmp_path: Path) -> None:
    class BrokenRow:
        def model_dump_json(self, *, exclude_none: bool) -> str:
            raise RuntimeError("simulated serialization failure")

    output_dir = tmp_path / "live-output"
    with pytest.raises(RuntimeError, match="simulated serialization failure"):
        run_eval_module._freeze_datasets({"recognition": [BrokenRow()]}, output_dir)
    assert not output_dir.exists()
    assert list(tmp_path.glob(".live-output.*")) == []


def test_live_output_staging_is_removed_when_manifest_write_fails(tmp_path: Path) -> None:
    class GoodRow:
        def model_dump_json(self, *, exclude_none: bool) -> str:
            return '{"id":"row-1"}'

    def fail_finalize(_: Path) -> None:
        raise RuntimeError("simulated run manifest failure")

    output_dir = tmp_path / "live-output"
    with pytest.raises(RuntimeError, match="simulated run manifest failure"):
        run_eval_module._freeze_datasets(
            {"recognition": [GoodRow()]}, output_dir, finalize=fail_finalize
        )
    assert not output_dir.exists()
    assert list(tmp_path.glob(".live-output.*")) == []


def _corrupt_pairs_dir(src: Path, dst: Path) -> None:
    """复制种子数据集，并把一行期望标签改错（触发阻断指标失败）。

    si-1 两报价完全相同，领域判定必为同款；把期望改为"异款"产生一个
    假阳性（FP），直接击穿 same_item_pairwise_precision 与 false_comparison_rate。
    """
    shutil.copytree(src, dst)
    pairs = dst / "same_item_pairs.jsonl"
    lines = pairs.read_text(encoding="utf-8").splitlines()
    row = json.loads(lines[0])
    assert row["id"] == "si-1"
    row["same_spu"] = False
    lines[0] = json.dumps(row, ensure_ascii=False)
    pairs.write_text("\n".join(lines), encoding="utf-8")


def test_gate_failure_exits_1(
    seed_dir: Path, tmp_path: Path, report_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    broken_dir = tmp_path / "broken"
    _corrupt_pairs_dir(seed_dir, broken_dir)
    code = eval_main(["--datasets-dir", str(broken_dir), "--report-dir", str(report_dir)])
    assert code == _GATE_FAIL
    out = capsys.readouterr().out
    assert "阻断指标未达标" in out
    assert "same_item_pairwise_precision" in out


def test_no_gate_bypasses_failure(seed_dir: Path, tmp_path: Path, report_dir: Path) -> None:
    broken_dir = tmp_path / "broken"
    _corrupt_pairs_dir(seed_dir, broken_dir)
    code = eval_main(
        [
            "--datasets-dir",
            str(broken_dir),
            "--report-dir",
            str(report_dir),
            "--no-gate",
        ]
    )
    assert code == _PASS
