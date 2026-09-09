"""机器可读的生产发布证据门禁。

该模块只验证报告中已经定义的精确字段和证据文件摘要，不把本地集成通过
推断为生产 HA、备份或观测系统通过。
"""

from __future__ import annotations

import hashlib
import json
import math
import shlex
import shutil
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any, cast

from pydantic import ValidationError

from shijiajing_agent.benchmark import BenchmarkReport
from shijiajing_agent.evals import validate_report_payload

RELEASE_GATE_SCHEMA_VERSION = "1.0"
PRODUCTION_EVIDENCE_CHECKS = (
    "postgres_ha",
    "backup_storage",
    "otel_collector",
)
PRODUCTION_EVIDENCE_REQUIRED_CLAIMS: Mapping[str, tuple[str, ...]] = {
    "postgres_ha": (
        "ha_failover",
        "connection_pool_load",
        "real_data_recovery",
    ),
    "backup_storage": (
        "encryption",
        "retention",
        "permissions",
        "cross_region_restore",
    ),
    "otel_collector": (
        "persistence",
        "alerts",
        "query",
        "permissions",
        "retention",
    ),
}


class ReleaseCheckStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    PENDING = "pending"


@dataclass(frozen=True)
class ReleaseCheck:
    check_id: str
    status: ReleaseCheckStatus
    reason: str
    evidence_path: str | None = None


@dataclass(frozen=True)
class ReleaseGateReport:
    schema_version: str
    ready: bool
    checks: tuple[ReleaseCheck, ...]

    @property
    def blockers(self) -> tuple[str, ...]:
        return tuple(
            check.check_id for check in self.checks if check.status is not ReleaseCheckStatus.PASSED
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": "ready" if self.ready else "not_ready",
            "ready": self.ready,
            "blockers": list(self.blockers),
            "checks": [
                {
                    "check_id": check.check_id,
                    "status": check.status.value,
                    "reason": check.reason,
                    "evidence_path": check.evidence_path,
                }
                for check in self.checks
            ],
        }


def evaluate_release_gate(
    *,
    verification_summary: Path | None = None,
    backup_summary: Path | None = None,
    eval_report: Path | None = None,
    benchmark_report: Path | None = None,
    production_evidence_manifest: Path | None = None,
    check_client_tools: bool = True,
) -> ReleaseGateReport:
    checks = [
        _check_phase2_verification(verification_summary),
        _check_backup_restore(backup_summary),
        _check_eval_report(eval_report),
        _check_benchmark_report(benchmark_report),
    ]
    if check_client_tools:
        checks.append(_check_client_tools())
    checks.extend(_check_production_evidence(production_evidence_manifest))
    return ReleaseGateReport(
        schema_version=RELEASE_GATE_SCHEMA_VERSION,
        ready=all(check.status is ReleaseCheckStatus.PASSED for check in checks),
        checks=tuple(checks),
    )


def build_production_evidence_manifest(
    output: Path, evidence_paths: Mapping[str, Path]
) -> dict[str, Any]:
    """生成不可覆盖的生产证据 manifest，并为每个文件计算 SHA-256。"""
    expected_ids = set(PRODUCTION_EVIDENCE_CHECKS)
    if set(evidence_paths) != expected_ids:
        raise ValueError("生产证据必须恰好包含 postgres_ha、backup_storage、otel_collector")
    output_path = output.resolve()
    if output_path.exists():
        raise ValueError("生产证据 manifest 已存在，拒绝覆盖")
    output_parent = output_path.parent
    checks: dict[str, dict[str, str]] = {}
    for check_id in PRODUCTION_EVIDENCE_CHECKS:
        source = Path(evidence_paths[check_id]).resolve()
        if not source.is_file():
            raise ValueError("生产证据文件不存在")
        try:
            relative = source.relative_to(output_parent)
        except ValueError as exc:
            raise ValueError("生产证据文件必须位于 manifest 目录内") from exc
        evidence_payload = _load_json(source)
        if evidence_payload is None:
            raise ValueError(f"{check_id} 生产证据必须是 JSON 对象")
        validation_error = _validate_production_evidence_document(check_id, evidence_payload)
        if validation_error is not None:
            raise ValueError(f"{check_id} 生产证据无效：{validation_error}")
        checks[check_id] = {
            "status": "verified",
            "evidence_path": relative.as_posix(),
            "sha256": _sha256_file(source),
        }
    payload: dict[str, Any] = {
        "schema_version": RELEASE_GATE_SCHEMA_VERSION,
        "environment": "prod",
        "checks": checks,
    }
    output_parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, staging_name = tempfile.mkstemp(
        prefix=f".{output_path.name}.", suffix=".tmp", dir=output_parent
    )
    staging_path = Path(staging_name)
    try:
        with open(file_descriptor, "w", encoding="utf-8", closefd=True) as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        if output_path.exists():
            raise ValueError("生产证据 manifest 已存在，拒绝覆盖")
        staging_path.replace(output_path)
    finally:
        staging_path.unlink(missing_ok=True)
    return payload


def _check_phase2_verification(path: Path | None) -> ReleaseCheck:
    check_id = "phase2_verification"
    payload = _load_json(path)
    if payload is None:
        return _pending(check_id, "缺少 PostgreSQL/OTLP verification summary", path)
    health_value = payload.get("health")
    if not isinstance(health_value, Mapping):
        return _failed(check_id, "verification summary 缺少 health 字段", path)
    health = cast(Mapping[str, Any], health_value)
    command_results_value = payload.get("command_results")
    if not isinstance(command_results_value, list):
        return _failed(check_id, "verification summary 缺少 command_results", path)
    command_results = cast(list[Any], command_results_value)
    if not _all_commands_successful(command_results):
        return _failed(check_id, "verification summary 存在失败命令", path)
    if (
        payload.get("status") == "passed"
        and payload.get("exit_code") == 0
        and health.get("postgres") == "healthy"
        and health.get("otel-collector") == "healthy"
    ):
        return _passed(check_id, "本地 PostgreSQL/OTLP verification 已通过", path)
    return _failed(check_id, "PostgreSQL/OTLP verification summary 未通过", path)


def _check_backup_restore(path: Path | None) -> ReleaseCheck:
    check_id = "postgres_backup_restore"
    payload = _load_json(path)
    if payload is None:
        return _pending(check_id, "缺少 PostgreSQL backup/restore summary", path)
    backup = payload.get("backup_restore")
    if not isinstance(backup, Mapping):
        return _failed(check_id, "summary 缺少 backup_restore 字段", path)
    backup_map = cast(Mapping[str, Any], backup)
    dump_value = backup_map.get("dump")
    if not isinstance(dump_value, str):
        return _failed(check_id, "backup/restore summary 缺少可读取 dump", path)
    try:
        dump_path = _resolve_summary_artifact(path, dump_value)
        if dump_path is None:
            return _failed(check_id, "backup/restore dump 必须位于 summary 证据目录内", path)
        dump_exists = dump_path.is_file()
        dump_size = dump_path.stat().st_size if dump_exists else 0
    except OSError:
        dump_exists = False
        dump_size = 0
    if not dump_exists:
        return _failed(check_id, "backup/restore summary 缺少可读取 dump", path)
    if dump_size <= 0:
        return _failed(check_id, "backup/restore dump 文件为空", path)
    command_results = payload.get("command_results")
    if not isinstance(command_results, list):
        return _failed(check_id, "backup/restore summary 缺少 command_results", path)
    raw_command_results = cast(list[Any], command_results)
    if not _has_successful_command(raw_command_results, "pg_dump") or not _has_successful_command(
        raw_command_results, "pg_restore"
    ):
        return _failed(check_id, "backup/restore 未记录成功的 pg_dump/pg_restore", path)
    if (
        backup_map.get("requested") is True
        and backup_map.get("status") == "passed"
        and backup_map.get("source_public_table_count")
        == backup_map.get("restored_public_table_count")
        and backup_map.get("sentinel_rows") == 1
    ):
        return _passed(check_id, "隔离数据库 backup/restore 校验已通过", path)
    return _failed(check_id, "PostgreSQL backup/restore 证据未通过", path)


def _has_successful_command(command_results: list[Any], executable: str) -> bool:
    for item in command_results:
        if not isinstance(item, Mapping):
            continue
        command_item = cast(Mapping[str, Any], item)
        command = command_item.get("command")
        if (
            command_item.get("status") == "passed"
            and command_item.get("exit_code") == 0
            and isinstance(command, str)
            and _command_contains_executable(command, executable)
        ):
            return True
    return False


def _command_contains_executable(command: str, executable: str) -> bool:
    """只接受命令参数中的独立 executable token，不接受子串伪造。"""
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        return False
    for token in tokens:
        normalized = token.replace("\\", "/").rstrip("/")
        basename = normalized.rsplit("/", 1)[-1]
        if basename in {executable, f"{executable}.exe"}:
            return True
    return False


def _all_commands_successful(command_results: list[Any]) -> bool:
    if not command_results:
        return False
    for item in command_results:
        if not isinstance(item, Mapping):
            return False
        command_item = cast(Mapping[str, Any], item)
        if command_item.get("status") != "passed" or command_item.get("exit_code") != 0:
            return False
    return True


def _check_eval_report(path: Path | None) -> ReleaseCheck:
    check_id = "formal_eval"
    payload = _load_json(path)
    if payload is None:
        return _pending(check_id, "缺少正式评测 JSON 报告", path)
    validation_error = validate_report_payload(payload)
    if validation_error is not None:
        return _failed(check_id, validation_error, path)
    if (
        payload.get("trust_level") == "frozen"
        and payload.get("label_method") == "adjudicated"
        and payload.get("metric_gate_passed") is True
        and payload.get("release_gate_eligible") is True
        and payload.get("release_gate_passed") is True
        and payload.get("blocking_failures") == []
        and payload.get("blocking_pending") == []
    ):
        return _passed(check_id, "正式评测发布门禁已通过", path)
    return _failed(check_id, "正式评测未达到 frozen/adjudicated 发布门禁", path)


def _check_benchmark_report(path: Path | None) -> ReleaseCheck:
    check_id = "formal_latency_gate"
    payload = _load_json(path)
    if payload is None:
        return _pending(check_id, "缺少正式性能门禁 JSON 报告", path)
    try:
        benchmark = BenchmarkReport.model_validate(payload)
    except ValidationError:
        return _failed(check_id, "正式性能报告结构无效", path)
    strategies = [result.strategy for result in benchmark.results]
    if len(strategies) != len(set(strategies)) or set(strategies) != {
        "weighted",
        "rrf",
        "weighted_rerank",
    }:
        return _failed(check_id, "正式性能报告必须包含三种策略且各出现一次", path)
    strategy = benchmark.gate_strategy
    threshold = benchmark.gate_max_p95_ms
    selected_result = next(
        (item for item in benchmark.results if item.strategy == strategy),
        None,
    )
    if (
        benchmark.source == "formal"
        and benchmark.gate_passed is True
        and isinstance(strategy, str)
        and strategy in {"weighted", "rrf", "weighted_rerank"}
        and isinstance(threshold, (int, float))
        and not isinstance(threshold, bool)
        and math.isfinite(float(threshold))
        and float(threshold) > 0
        and benchmark.gate_failures == []
        and selected_result is not None
        and selected_result.duration_ms_p95 <= float(threshold)
    ):
        return _passed(check_id, "正式性能 p95 门禁已通过", path)
    return _failed(check_id, "性能报告不是 formal 或 gate_passed 不为 true", path)


def _check_client_tools() -> ReleaseCheck:
    missing = [name for name in ("pg_dump", "pg_restore") if shutil.which(name) is None]
    if not missing:
        return _passed("postgres_client_tools", "主机 pg_dump/pg_restore 均可用", None)
    return _failed(
        "postgres_client_tools",
        "主机缺少 PostgreSQL client tools: " + ", ".join(missing),
        None,
    )


def _check_production_evidence(path: Path | None) -> list[ReleaseCheck]:
    if path is None:
        return [
            _pending(check_id, "缺少生产外部系统证据 manifest", None)
            for check_id in PRODUCTION_EVIDENCE_CHECKS
        ]
    payload = _load_json(path)
    if payload is None:
        return [
            _failed(check_id, "生产外部系统证据 manifest 无法读取", path)
            for check_id in PRODUCTION_EVIDENCE_CHECKS
        ]
    if (
        payload.get("schema_version") != RELEASE_GATE_SCHEMA_VERSION
        or payload.get("environment") != "prod"
    ):
        return [
            _failed(check_id, "生产外部系统证据 manifest schema/environment 无效", path)
            for check_id in PRODUCTION_EVIDENCE_CHECKS
        ]
    raw_checks_value = payload.get("checks")
    if not isinstance(raw_checks_value, Mapping):
        return [
            _failed(check_id, "生产外部系统证据 manifest 缺少 checks", path)
            for check_id in PRODUCTION_EVIDENCE_CHECKS
        ]
    raw_checks = cast(Mapping[str, Any], raw_checks_value)
    if set(raw_checks) != set(PRODUCTION_EVIDENCE_CHECKS):
        return [
            _failed(check_id, "生产外部系统证据 manifest checks 集合无效", path)
            for check_id in PRODUCTION_EVIDENCE_CHECKS
        ]
    return [
        _check_production_evidence_item(check_id, raw_checks, path)
        for check_id in PRODUCTION_EVIDENCE_CHECKS
    ]


def _check_production_evidence_item(
    check_id: str, raw_checks: Mapping[str, Any], manifest_path: Path
) -> ReleaseCheck:
    raw_item_value = raw_checks.get(check_id)
    if not isinstance(raw_item_value, Mapping):
        return _failed(check_id, "生产证据条目未标记为 verified", manifest_path)
    raw_item = cast(Mapping[str, Any], raw_item_value)
    if raw_item.get("status") != "verified":
        return _failed(check_id, "生产证据条目未标记为 verified", manifest_path)
    evidence_name = raw_item.get("evidence_path")
    expected_sha256 = raw_item.get("sha256")
    if not isinstance(evidence_name, str) or not isinstance(expected_sha256, str):
        return _failed(check_id, "生产证据条目缺少 evidence_path/sha256", manifest_path)
    if len(expected_sha256) != 64 or any(
        char not in "0123456789abcdef" for char in expected_sha256
    ):
        return _failed(check_id, "生产证据 sha256 格式无效", manifest_path)
    relative_path = Path(evidence_name)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        return _failed(
            check_id, "生产证据 evidence_path 必须是 manifest 目录内的相对路径", manifest_path
        )
    evidence_path = (manifest_path.parent / relative_path).resolve()
    try:
        evidence_path.relative_to(manifest_path.parent.resolve())
    except ValueError:
        return _failed(check_id, "生产证据 evidence_path 超出 manifest 目录", manifest_path)
    if not evidence_path.is_file():
        return _failed(check_id, "生产证据文件不存在", evidence_path)
    digest = hashlib.sha256(evidence_path.read_bytes()).hexdigest()
    if digest != expected_sha256:
        return _failed(check_id, "生产证据 sha256 不匹配", evidence_path)
    evidence_payload = _load_json(evidence_path)
    if evidence_payload is None:
        return _failed(check_id, "生产证据必须是 JSON 对象", evidence_path)
    validation_error = _validate_production_evidence_document(check_id, evidence_payload)
    if validation_error is not None:
        return _failed(check_id, validation_error, evidence_path)
    return _passed(check_id, "生产证据文件摘要已校验", evidence_path)


def _validate_production_evidence_document(check_id: str, payload: Mapping[str, Any]) -> str | None:
    if payload.get("schema_version") != RELEASE_GATE_SCHEMA_VERSION:
        return "生产证据 schema_version 无效"
    if payload.get("environment") != "prod":
        return "生产证据 environment 必须为 prod"
    if payload.get("check_id") != check_id:
        return "生产证据 check_id 与 manifest 条目不一致"
    if payload.get("status") != "passed":
        return "生产证据 status 必须为 passed"
    verified_at = payload.get("verified_at")
    if not isinstance(verified_at, str) or not _is_utc_timestamp(verified_at):
        return "生产证据 verified_at 必须是带 UTC 时区的 ISO-8601 时间"
    claims_value = payload.get("claims")
    if not isinstance(claims_value, Mapping):
        return "生产证据缺少 claims"
    claims = cast(Mapping[str, Any], claims_value)
    required_claims = set(PRODUCTION_EVIDENCE_REQUIRED_CLAIMS[check_id])
    if set(claims) != required_claims:
        return "生产证据 claims 集合与固定验收项不一致"
    if any(claims[claim_id] != "passed" for claim_id in required_claims):
        return "生产证据 claims 必须全部为 passed"
    return None


def _is_utc_timestamp(value: str) -> bool:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() == timedelta(0)


def _resolve_summary_artifact(summary_path: Path | None, raw_path: str) -> Path | None:
    if summary_path is None:
        return None
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = summary_path.parent / candidate
    resolved = candidate.resolve()
    summary_dir = summary_path.parent.resolve()
    try:
        resolved.relative_to(summary_dir)
    except ValueError:
        return None
    if candidate.is_symlink():
        return None
    return resolved


def _load_json(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return cast(dict[str, Any], payload) if isinstance(payload, dict) else None


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _passed(check_id: str, reason: str, path: Path | None) -> ReleaseCheck:
    return ReleaseCheck(check_id, ReleaseCheckStatus.PASSED, reason, str(path) if path else None)


def _failed(check_id: str, reason: str, path: Path | None) -> ReleaseCheck:
    return ReleaseCheck(check_id, ReleaseCheckStatus.FAILED, reason, str(path) if path else None)


def _pending(check_id: str, reason: str, path: Path | None) -> ReleaseCheck:
    return ReleaseCheck(check_id, ReleaseCheckStatus.PENDING, reason, str(path) if path else None)
