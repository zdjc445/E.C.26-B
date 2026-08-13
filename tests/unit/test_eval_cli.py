"""评测 CLI（shijiajing-eval）离线路径测试（§24 阶段 6 离线评测脚本）。

- 离线运行种子数据集 → 退出码 0、报告文件落盘、冻结报告可写；
- 数据集目录缺失 / 为空 → 退出码 2（配置错误）；
- 存在阻断指标不达标的数据 → 退出码 1 且输出失败明细；
  ``--no-gate`` 跳过门禁仍返回 0。
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from shijiajing_agent.evals import default_datasets_dir
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


def test_offline_run_seed_datasets_passes(
    seed_dir: Path, report_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = eval_main(["--datasets-dir", str(seed_dir), "--report-dir", str(report_dir)])
    assert code == _PASS
    assert "阻断指标全部达标" in capsys.readouterr().out
    json_report = json.loads((report_dir / "eval_report.json").read_text(encoding="utf-8"))
    assert json_report["gate"] is True
    assert (report_dir / "eval_report.md").exists()


def test_frozen_flag_writes_frozen_report(seed_dir: Path, report_dir: Path) -> None:
    code = eval_main(["--datasets-dir", str(seed_dir), "--report-dir", str(report_dir), "--frozen"])
    assert code == _PASS
    frozen = report_dir / "frozen_eval_report.md"
    assert frozen.exists()
    assert "阻断指标全部达标" in frozen.read_text(encoding="utf-8")


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
