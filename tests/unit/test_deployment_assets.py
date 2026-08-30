"""二期外部依赖部署资产的静态契约。"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parents[2]


def test_phase2_compose_requires_secret_and_pins_services() -> None:
    compose = (ROOT / "deploy" / "phase2" / "docker-compose.yml").read_text(encoding="utf-8")

    assert "image: postgres:16-alpine" in compose
    assert "POSTGRES_PASSWORD:?POSTGRES_PASSWORD must be set" in compose
    assert "image: ${OTEL_COLLECTOR_IMAGE:-otel/opentelemetry-collector-contrib:0.123.0}" in compose
    assert "./otel-collector-config.yaml:/etc/otelcol-contrib/config.yaml:ro" in compose


def test_phase2_collector_receives_otlp_http_and_exports_debug() -> None:
    collector = (ROOT / "deploy" / "phase2" / "otel-collector-config.yaml").read_text(
        encoding="utf-8"
    )

    assert "endpoint: 0.0.0.0:4318" in collector
    assert "receivers:" in collector
    assert "exporters:" in collector
    assert "- debug" in collector


def test_phase2_verification_script_is_strict_and_runs_both_gates() -> None:
    script = (ROOT / "deploy" / "phase2" / "verify.ps1").read_text(encoding="utf-8")

    assert '"SHIJIAJING_REQUIRE_POSTGRES"' in script
    assert '"SHIJIAJING_TEST_POSTGRES_DSN"' in script
    assert '"SHIJIAJING_TRACE_BACKEND"' in script
    assert '"SHIJIAJING_TRACE_DSN"' in script
    for test_file in (
        "tests/contract/test_native_checkpointers.py",
        "tests/contract/test_request_ledger.py",
        "tests/contract/test_memory_adapters.py",
        "tests/contract/test_cache_adapters.py",
        "tests/contract/test_event_store.py",
    ):
        assert test_file in script
    assert (
        'Invoke-UvCommand @("run", "pytest", "-q", "-m", "integration", '
        "$integrationTestFile)" in script
    )
    assert (
        'Invoke-UvCommand @("run", "shijiajing-preflight", "--storage-only", '
        '"--verify-trace", "--json")' in script
    )
    assert 'Invoke-ComposeCommand @("down")' in script
    assert "[switch]$VerifyBackupRestore" in script
    assert '"pg_dump"' in script
    assert '"pg_restore"' in script
    assert "postgres-container.dump" in script
    assert '"SHIJIAJING_POSTGRES_POOL_MIN_SIZE"' in script
    assert '"SHIJIAJING_POSTGRES_POOL_MAX_SIZE"' in script
    assert '"SHIJIAJING_POSTGRES_POOL_TIMEOUT_SECONDS"' in script
    assert "postgres_pool = $script:PostgresPoolEvidence" in script
    assert "backup_restore = $script:BackupEvidence" in script


def test_phase2_verification_script_archives_evidence_and_preserves_failure_status() -> None:
    script = (ROOT / "deploy" / "phase2" / "verify.ps1").read_text(encoding="utf-8")

    assert "[string]$EvidenceDir" in script
    assert "Start-Transcript -Path $transcriptPath" in script
    assert "summary.json" in script
    assert ".summary.json.tmp" in script
    assert "Move-Item -LiteralPath $summaryTempPath -Destination $summaryPath" in script
    assert "拒绝覆盖：$summaryPath" in script
    assert '$status = "passed"' in script
    assert "catch {" in script
    assert "$script:EvidenceCommands.Add" in script
    assert "$script:EvidenceResults.Add" in script
    assert "$commandExitCode = $LASTEXITCODE" in script
    assert "command_results = $script:EvidenceResults.ToArray()" in script
    assert "$script:HealthStatus = [ordered]@{" in script
    assert "health = $script:HealthStatus" in script
    assert "$script:HealthStatus[$ServiceName]" in script
    assert 'exit_code = if ($status -eq "passed")' in script
    assert '[string]$ProjectName = "shijiajing-phase2-$PID"' in script
    assert '"--project-name", $ProjectName' in script


def test_phase2_storage_runbooks_match_the_operational_cli_contract() -> None:
    operations = (ROOT / "docs" / "operations_phase2.md").read_text(encoding="utf-8")
    repair = (ROOT / "docs" / "operations" / "event_repair.md").read_text(encoding="utf-8")

    assert "operations/event_repair.md" in operations
    assert "shijiajing-preflight" in operations
    assert "shijiajing-repair-events" in repair
    assert "request_result_committed" in repair
    assert "--dry-run" in repair
    assert "--apply" in repair


def test_docs_do_not_reference_removed_plan_sections() -> None:
    documentation = "\n".join(
        path.read_text(encoding="utf-8")
        for path in [
            ROOT / "README.md",
            ROOT / ".env.example",
            *sorted((ROOT / "docs").glob("*.md")),
        ]
    )

    for removed_reference in ("§23", "§24", "§25", "§22.3", "§13.7"):
        assert removed_reference not in documentation
