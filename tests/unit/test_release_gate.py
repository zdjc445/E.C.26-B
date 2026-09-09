"""生产发布证据门禁测试。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from shijiajing_agent.evals import DATASET_FILES, EVAL_REPORT_SCHEMA_VERSION
from shijiajing_agent.release_gate import (
    PRODUCTION_EVIDENCE_REQUIRED_CLAIMS,
    evaluate_release_gate,
)
from shijiajing_agent.tools import cli_support, release_check


def _write(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _write_production_manifest(path: Path) -> None:
    checks = {}
    for check_id, claim_ids in PRODUCTION_EVIDENCE_REQUIRED_CLAIMS.items():
        evidence = path.parent / f"{check_id}.json"
        evidence.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "environment": "prod",
                    "check_id": check_id,
                    "status": "passed",
                    "verified_at": "2026-08-22T00:00:00Z",
                    "claims": {claim_id: "passed" for claim_id in claim_ids},
                }
            ),
            encoding="utf-8",
        )
        checks[check_id] = {
            "status": "verified",
            "evidence_path": evidence.name,
            "sha256": hashlib.sha256(evidence.read_bytes()).hexdigest(),
        }
    _write(
        path,
        {"schema_version": "1.0", "environment": "prod", "checks": checks},
    )


def _local_summary() -> dict[str, object]:
    return {
        "status": "passed",
        "exit_code": 0,
        "command_results": [{"command": "verification", "status": "passed", "exit_code": 0}],
        "health": {"postgres": "healthy", "otel-collector": "healthy"},
    }


def _backup_summary(dump: Path) -> dict[str, object]:
    return {
        "command_results": [
            {"command": "pg_dump --format=custom", "status": "passed", "exit_code": 0},
            {"command": "pg_restore --list", "status": "passed", "exit_code": 0},
        ],
        "backup_restore": {
            "requested": True,
            "status": "passed",
            "dump": str(dump),
            "source_public_table_count": 10,
            "restored_public_table_count": 10,
            "sentinel_rows": 1,
        },
    }


def _formal_eval_report() -> dict[str, object]:
    thresholds = {
        "same_item_pairwise_precision": ("ge", 0.98),
        "false_comparison_rate": ("le", 0.01),
        "hard_filter_satisfaction_rate": ("eq", 1.0),
        "explanation_factual_consistency_rate": ("eq", 1.0),
    }
    return {
        "schema_version": EVAL_REPORT_SCHEMA_VERSION,
        "generated_at": "2026-08-22T00:00:00+00:00",
        "source": "live",
        "gate": True,
        "trust_level": "frozen",
        "label_method": "adjudicated",
        "metric_gate_passed": True,
        "release_gate_eligible": True,
        "release_gate_passed": True,
        "pending_reasons": [],
        "blocking_failures": [],
        "blocking_pending": [],
        "datasets": {
            kind: {"kind": kind, "n_rows": 1, "n_recorded": 1, "digest": "a" * 16}
            for kind in DATASET_FILES
        },
        "metrics": [
            {
                "name": name,
                "value": value,
                "n": 1,
                "pending": 0,
                "source": "live",
                "threshold": {"op": op, "value": value, "blocking": True},
                "passed": True,
                "note": "",
            }
            for name, (op, value) in thresholds.items()
        ],
    }


def _formal_benchmark_report() -> dict[str, object]:
    return {
        "generated_at": "2026-08-22T00:00:00+00:00",
        "source": "formal",
        "warmup_count": 0,
        "iteration_count": 1,
        "results": [
            {
                "strategy": strategy,
                "sample_dataset_count": 1,
                "iteration_count": 1,
                "duration_ms_p50": 1.0,
                "duration_ms_p95": 1.0,
                "duration_ms_p99": 1.0,
                "duration_ms_min": 1.0,
                "duration_ms_max": 1.0,
            }
            for strategy in ("weighted", "rrf", "weighted_rerank")
        ],
        "python_version": "3.12.0",
        "platform": "test",
        "gate_strategy": "weighted",
        "gate_max_p95_ms": 10.0,
        "gate_passed": True,
        "gate_failures": [],
    }


def test_release_gate_fails_closed_without_formal_and_production_evidence(tmp_path: Path) -> None:
    verification = tmp_path / "verification.json"
    backup = tmp_path / "backup.json"
    evaluation = tmp_path / "eval.json"
    benchmark = tmp_path / "benchmark.json"
    dump = tmp_path / "backup.dump"
    dump.write_bytes(b"custom-format-dump")
    _write(verification, _local_summary())
    _write(backup, _backup_summary(dump))
    _write(evaluation, {"release_gate_eligible": False, "release_gate_passed": False})
    _write(benchmark, {"source": "seed_offline", "gate_passed": None})

    report = evaluate_release_gate(
        verification_summary=verification,
        backup_summary=backup,
        eval_report=evaluation,
        benchmark_report=benchmark,
        check_client_tools=False,
    )

    assert report.ready is False
    assert report.blockers == (
        "formal_eval",
        "formal_latency_gate",
        "postgres_ha",
        "backup_storage",
        "otel_collector",
    )


def test_release_gate_passes_only_when_all_machine_checks_and_hashes_pass(
    tmp_path: Path, monkeypatch
) -> None:
    verification = tmp_path / "verification.json"
    backup = tmp_path / "backup.json"
    evaluation = tmp_path / "eval.json"
    benchmark = tmp_path / "benchmark.json"
    manifest = tmp_path / "production.json"
    dump = tmp_path / "backup.dump"
    dump.write_bytes(b"custom-format-dump")
    _write(verification, _local_summary())
    _write(backup, _backup_summary(dump))
    _write(evaluation, _formal_eval_report())
    _write(benchmark, _formal_benchmark_report())
    _write_production_manifest(manifest)
    monkeypatch.setattr("shutil.which", lambda name: name)

    report = evaluate_release_gate(
        verification_summary=verification,
        backup_summary=backup,
        eval_report=evaluation,
        benchmark_report=benchmark,
        production_evidence_manifest=manifest,
    )

    assert report.ready is True
    assert report.blockers == ()


def test_release_gate_rejects_tampered_production_evidence(tmp_path: Path) -> None:
    manifest = tmp_path / "production.json"
    _write_production_manifest(manifest)
    (tmp_path / "postgres_ha.json").write_text("tampered", encoding="utf-8")

    report = evaluate_release_gate(
        production_evidence_manifest=manifest,
        check_client_tools=False,
    )

    assert report.ready is False
    postgres_check = next(check for check in report.checks if check.check_id == "postgres_ha")
    assert postgres_check.reason == "生产证据 sha256 不匹配"


def test_release_gate_rejects_evidence_path_escape(tmp_path: Path) -> None:
    manifest = tmp_path / "production.json"
    escape_path = str(Path("..") / "outside.json")
    _write(
        manifest,
        {
            "schema_version": "1.0",
            "environment": "prod",
            "checks": {
                check_id: {
                    "status": "verified",
                    "evidence_path": escape_path,
                    "sha256": "0" * 64,
                }
                for check_id in ("postgres_ha", "backup_storage", "otel_collector")
            },
        },
    )

    report = evaluate_release_gate(
        production_evidence_manifest=manifest,
        check_client_tools=False,
    )

    production_checks = {
        "postgres_ha",
        "backup_storage",
        "otel_collector",
    }
    assert all(
        check.reason == "生产证据 evidence_path 必须是 manifest 目录内的相对路径"
        for check in report.checks
        if check.check_id in production_checks
    )


def test_release_check_cli_is_fail_closed_without_evidence(capsys) -> None:
    assert release_check.main(["--json"]) == 1

    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "not_ready"
    assert output["ready"] is False
    assert "formal_eval" in output["blockers"]


def test_release_check_cli_reconfigures_output_streams(monkeypatch) -> None:
    class Stream:
        def __init__(self) -> None:
            self.calls: list[dict[str, str]] = []
            self.output = ""

        def reconfigure(self, **kwargs: str) -> None:
            self.calls.append(kwargs)

        def write(self, value: str) -> int:
            self.output += value
            return len(value)

        def flush(self) -> None:
            return None

    stdout = Stream()
    stderr = Stream()
    monkeypatch.setattr(cli_support.sys, "stdout", stdout)
    monkeypatch.setattr(cli_support.sys, "stderr", stderr)

    assert release_check.main(["--json"]) == 1

    assert stdout.calls == [{"encoding": "utf-8", "errors": "replace"}]
    assert stderr.calls == [{"encoding": "utf-8", "errors": "replace"}]


def test_release_check_create_manifest_cli_hashes_files_and_refuses_overwrite(
    tmp_path: Path, capsys
) -> None:
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    evidence = {}
    for check_id, claim_ids in PRODUCTION_EVIDENCE_REQUIRED_CLAIMS.items():
        path = evidence_dir / f"{check_id}.json"
        path.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "environment": "prod",
                    "check_id": check_id,
                    "status": "passed",
                    "verified_at": "2026-08-22T00:00:00Z",
                    "claims": {claim_id: "passed" for claim_id in claim_ids},
                }
            ),
            encoding="utf-8",
        )
        evidence[check_id] = path
    manifest = evidence_dir / "production.json"

    args = ["create-manifest", "--output", str(manifest)]
    for check_id, path in evidence.items():
        args.extend([f"--{check_id.replace('_', '-')}", str(path)])

    assert release_check.main(args) == 0
    assert manifest.is_file()
    assert release_check.main(args) == 2
    assert "拒绝覆盖" in capsys.readouterr().err
    report = evaluate_release_gate(
        production_evidence_manifest=manifest,
        check_client_tools=False,
    )
    assert all(
        check.status.value == "passed"
        for check in report.checks
        if check.check_id in {"postgres_ha", "backup_storage", "otel_collector"}
    )


def test_release_gate_rejects_incomplete_production_claims(tmp_path: Path) -> None:
    manifest = tmp_path / "production.json"
    evidence = tmp_path / "postgres_ha.json"
    evidence.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "environment": "prod",
                "check_id": "postgres_ha",
                "status": "passed",
                "verified_at": "2026-08-22T00:00:00Z",
                "claims": {"ha_failover": "passed"},
            }
        ),
        encoding="utf-8",
    )
    checks = {
        check_id: {
            "status": "verified",
            "evidence_path": evidence.name,
            "sha256": hashlib.sha256(evidence.read_bytes()).hexdigest(),
        }
        for check_id in PRODUCTION_EVIDENCE_REQUIRED_CLAIMS
    }
    _write(manifest, {"schema_version": "1.0", "environment": "prod", "checks": checks})

    report = evaluate_release_gate(
        production_evidence_manifest=manifest,
        check_client_tools=False,
    )

    postgres_check = next(check for check in report.checks if check.check_id == "postgres_ha")
    assert postgres_check.reason == "生产证据 claims 集合与固定验收项不一致"


def test_release_gate_rejects_backup_dump_outside_summary_directory(tmp_path: Path) -> None:
    summary_dir = tmp_path / "summary"
    summary_dir.mkdir()
    dump = tmp_path / "outside.dump"
    dump.write_bytes(b"custom-format-dump")
    summary = summary_dir / "backup.json"
    _write(summary, _backup_summary(dump))

    report = evaluate_release_gate(backup_summary=summary, check_client_tools=False)

    backup_check = next(
        check for check in report.checks if check.check_id == "postgres_backup_restore"
    )
    assert backup_check.reason == "backup/restore dump 必须位于 summary 证据目录内"


def test_release_gate_rejects_similar_but_different_client_commands(tmp_path: Path) -> None:
    dump = tmp_path / "backup.dump"
    dump.write_bytes(b"custom-format-dump")
    summary = tmp_path / "backup.json"
    payload = _backup_summary(dump)
    payload["command_results"] = [
        {"command": "pg_dump-malicious --format=custom", "status": "passed", "exit_code": 0},
        {"command": "pg_restore-malicious --list", "status": "passed", "exit_code": 0},
    ]
    _write(summary, payload)

    report = evaluate_release_gate(backup_summary=summary, check_client_tools=False)

    backup_check = next(
        check for check in report.checks if check.check_id == "postgres_backup_restore"
    )
    assert backup_check.reason == "backup/restore 未记录成功的 pg_dump/pg_restore"


def test_release_gate_rejects_unknown_manifest_check(tmp_path: Path) -> None:
    manifest = tmp_path / "production.json"
    _write(
        manifest,
        {
            "schema_version": "1.0",
            "environment": "prod",
            "checks": {
                "postgres_ha": {},
                "backup_storage": {},
                "otel_collector": {},
                "unknown": {},
            },
        },
    )

    report = evaluate_release_gate(
        production_evidence_manifest=manifest,
        check_client_tools=False,
    )

    assert all(
        check.reason == "生产外部系统证据 manifest checks 集合无效"
        for check in report.checks
        if check.check_id in PRODUCTION_EVIDENCE_REQUIRED_CLAIMS
    )


def test_release_gate_rejects_incomplete_formal_reports(tmp_path: Path) -> None:
    evaluation = tmp_path / "eval.json"
    benchmark = tmp_path / "benchmark.json"
    _write(
        evaluation,
        {
            "trust_level": "frozen",
            "label_method": "adjudicated",
            "release_gate_eligible": True,
            "release_gate_passed": True,
        },
    )
    _write(benchmark, {"source": "formal", "gate_passed": True})

    report = evaluate_release_gate(
        eval_report=evaluation,
        benchmark_report=benchmark,
        check_client_tools=False,
    )

    assert next(
        check for check in report.checks if check.check_id == "formal_eval"
    ).status.value == ("failed")
    assert (
        next(
            check for check in report.checks if check.check_id == "formal_latency_gate"
        ).status.value
        == "failed"
    )


def test_release_gate_rejects_formal_flags_without_blocking_metrics(tmp_path: Path) -> None:
    evaluation = _formal_eval_report()
    evaluation["metrics"] = []
    evaluation_path = tmp_path / "eval.json"
    _write(evaluation_path, evaluation)

    report = evaluate_release_gate(eval_report=evaluation_path, check_client_tools=False)

    formal_check = next(check for check in report.checks if check.check_id == "formal_eval")
    assert formal_check.reason == "正式评测报告 metrics 不能为空"


def test_release_gate_rejects_formal_benchmark_missing_strategy(tmp_path: Path) -> None:
    benchmark = _formal_benchmark_report()
    benchmark["results"] = benchmark["results"][:2]  # type: ignore[index]
    benchmark_path = tmp_path / "benchmark.json"
    _write(benchmark_path, benchmark)

    report = evaluate_release_gate(
        benchmark_report=benchmark_path,
        check_client_tools=False,
    )

    latency_check = next(
        check for check in report.checks if check.check_id == "formal_latency_gate"
    )
    assert latency_check.reason == "正式性能报告必须包含三种策略且各出现一次"


def test_release_gate_rejects_failed_verification_command(tmp_path: Path) -> None:
    verification = tmp_path / "verification.json"
    _write(
        verification,
        {
            "status": "passed",
            "exit_code": 0,
            "command_results": [{"command": "verification", "status": "failed", "exit_code": 1}],
            "health": {"postgres": "healthy", "otel-collector": "healthy"},
        },
    )

    report = evaluate_release_gate(
        verification_summary=verification,
        check_client_tools=False,
    )

    verification_check = next(
        check for check in report.checks if check.check_id == "phase2_verification"
    )
    assert verification_check.reason == "verification summary 存在失败命令"
