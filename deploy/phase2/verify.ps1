[CmdletBinding()]
param(
    [int]$PostgresPort = 55432,
    [int]$OtlpHttpPort = 44318,
    [int]$OtlpGrpcPort = 44317,
    [int]$HealthTimeoutSeconds = 120,
    [string]$EvidenceDir = (Join-Path (Get-Location) "reports/phase2-verification"),
    [string]$ProjectName = "shijiajing-phase2-$PID",
    [switch]$VerifyBackupRestore,
    [switch]$KeepServices
)

$ErrorActionPreference = "Stop"

$composeFile = Join-Path $PSScriptRoot "docker-compose.yml"
$envFile = Join-Path $PSScriptRoot ".env.example"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$composeArgs = @(
    "--project-name", $ProjectName,
    "--env-file", $envFile,
    "--file", $composeFile
)

$evidenceRoot = [System.IO.Path]::GetFullPath($EvidenceDir)
$runId = "run-" + (Get-Date -Format "yyyyMMdd-HHmmss-fff")
$runEvidenceDir = Join-Path $evidenceRoot $runId
New-Item -ItemType Directory -Path $runEvidenceDir -Force | Out-Null
$transcriptPath = Join-Path $runEvidenceDir "transcript.log"
$summaryPath = Join-Path $runEvidenceDir "summary.json"
$startedAt = (Get-Date).ToUniversalTime().ToString("o")
$status = "failed"
$errorMessage = $null
$transcriptStarted = $false
$locationPushed = $false
$script:EvidenceCommands = [System.Collections.Generic.List[string]]::new()
$script:EvidenceResults = [System.Collections.Generic.List[object]]::new()
$script:HealthStatus = [ordered]@{
    postgres = "not_started"
    "otel-collector" = "not_started"
}
$script:BackupEvidence = [ordered]@{
    requested = [bool]$VerifyBackupRestore
    status = if ($VerifyBackupRestore) { "not_started" } else { "not_requested" }
    dump = $null
    source_public_table_count = $null
    restored_public_table_count = $null
    sentinel_rows = $null
    error = $null
}
Start-Transcript -Path $transcriptPath -Force | Out-Null
$transcriptStarted = $true

$environmentNames = @(
    "POSTGRES_PASSWORD",
    "SHIJIAJING_POSTGRES_PUBLISHED_PORT",
    "SHIJIAJING_OTLP_HTTP_PUBLISHED_PORT",
    "SHIJIAJING_OTLP_GRPC_PUBLISHED_PORT",
    "SHIJIAJING_TEST_POSTGRES_DSN",
    "SHIJIAJING_REQUIRE_POSTGRES",
    "SHIJIAJING_CHECKPOINT_BACKEND",
    "SHIJIAJING_CHECKPOINT_DSN",
    "SHIJIAJING_GRAPH_PERSISTENCE_MODE",
    "SHIJIAJING_REQUEST_LEDGER_BACKEND",
    "SHIJIAJING_REQUEST_LEDGER_DSN",
    "SHIJIAJING_MEMORY_BACKEND",
    "SHIJIAJING_MEMORY_DSN",
    "SHIJIAJING_CACHE_BACKEND",
    "SHIJIAJING_CACHE_DSN",
    "SHIJIAJING_EVENT_STORE_BACKEND",
    "SHIJIAJING_EVENT_STORE_DSN",
    "SHIJIAJING_TRACE_BACKEND",
    "SHIJIAJING_TRACE_DSN",
    "SHIJIAJING_POSTGRES_POOL_MIN_SIZE",
    "SHIJIAJING_POSTGRES_POOL_MAX_SIZE",
    "SHIJIAJING_POSTGRES_POOL_TIMEOUT_SECONDS"
)
$previousEnvironment = @{}
foreach ($environmentName in $environmentNames) {
    $previousEnvironment[$environmentName] = [Environment]::GetEnvironmentVariable($environmentName)
}
$script:PostgresPoolEvidence = [ordered]@{
    min_size = $null
    max_size = $null
    timeout_seconds = $null
}

function Invoke-ComposeCommand {
    param([string[]]$CommandArgs)

    $commandText = "docker compose $($composeArgs -join ' ') $($CommandArgs -join ' ')"
    $script:EvidenceCommands.Add($commandText)
    $commandStartedAt = (Get-Date).ToUniversalTime().ToString("o")
    & docker compose @composeArgs @CommandArgs
    $commandExitCode = $LASTEXITCODE
    $script:EvidenceResults.Add([pscustomobject]@{
        command = $commandText
        started_at = $commandStartedAt
        ended_at = (Get-Date).ToUniversalTime().ToString("o")
        exit_code = $commandExitCode
        status = if ($commandExitCode -eq 0) { "passed" } else { "failed" }
    })
    if ($commandExitCode -ne 0) {
        throw "docker compose 命令失败：$($CommandArgs -join ' ')"
    }
}

function Invoke-ComposeScalar {
    param([string[]]$CommandArgs)

    $commandText = "docker compose $($composeArgs -join ' ') $($CommandArgs -join ' ')"
    $script:EvidenceCommands.Add($commandText)
    $commandStartedAt = (Get-Date).ToUniversalTime().ToString("o")
    $output = (& docker compose @composeArgs @CommandArgs 2>&1 | Out-String).Trim()
    $commandExitCode = $LASTEXITCODE
    $script:EvidenceResults.Add([pscustomobject]@{
        command = $commandText
        started_at = $commandStartedAt
        ended_at = (Get-Date).ToUniversalTime().ToString("o")
        exit_code = $commandExitCode
        status = if ($commandExitCode -eq 0) { "passed" } else { "failed" }
        output = $output
    })
    if ($commandExitCode -ne 0) {
        throw "docker compose 命令失败：$($CommandArgs -join ' ')"
    }
    return $output
}

function Get-ServiceHealth {
    param([string]$ServiceName)

    $containerId = (& docker compose @composeArgs ps -q $ServiceName).Trim()
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($containerId)) {
        $script:HealthStatus[$ServiceName] = "missing"
        return "missing"
    }
    $health = (& docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' $containerId).Trim()
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($health)) {
        $health = "unknown"
    }
    $script:HealthStatus[$ServiceName] = $health
    return $health
}

function Wait-HealthyServices {
    param([int]$TimeoutSeconds)

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $postgresHealth = "missing"
    $collectorHealth = "missing"
    while ((Get-Date) -lt $deadline) {
        $postgresHealth = Get-ServiceHealth "postgres"
        $collectorHealth = Get-ServiceHealth "otel-collector"
        if ($postgresHealth -eq "healthy" -and $collectorHealth -eq "healthy") {
            return
        }
        Start-Sleep -Seconds 2
    }
    throw "外部依赖未健康：postgres=$postgresHealth，otel-collector=$collectorHealth"
}

function Invoke-UvCommand {
    param([string[]]$CommandArgs)

    $commandText = "uv $($CommandArgs -join ' ')"
    $script:EvidenceCommands.Add($commandText)
    $commandStartedAt = (Get-Date).ToUniversalTime().ToString("o")
    & uv @CommandArgs
    $commandExitCode = $LASTEXITCODE
    $script:EvidenceResults.Add([pscustomobject]@{
        command = $commandText
        started_at = $commandStartedAt
        ended_at = (Get-Date).ToUniversalTime().ToString("o")
        exit_code = $commandExitCode
        status = if ($commandExitCode -eq 0) { "passed" } else { "failed" }
    })
    if ($commandExitCode -ne 0) {
        throw "uv 命令失败：$($CommandArgs -join ' ')"
    }
}

function Invoke-BackupRestoreVerification {
    $script:BackupEvidence.status = "running"
    $backupPathInContainer = "/tmp/phase2-postgres-backup.dump"
    $restoreDatabase = "phase2_restore"
    $sentinelTable = "phase2_backup_verification"
    $tableCountQuery = "SELECT count(*) FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace WHERE c.relkind IN ('r','p') AND n.nspname = 'public';"
    $sentinelCreateQuery = "DROP TABLE IF EXISTS public.$sentinelTable; CREATE TABLE public.$sentinelTable (marker text NOT NULL); INSERT INTO public.$sentinelTable (marker) VALUES ('phase2-backup-sentinel');"
    $sentinelCountQuery = "SELECT count(*) FROM public.$sentinelTable WHERE marker = 'phase2-backup-sentinel';"
    $sentinelDropQuery = "DROP TABLE IF EXISTS public.$sentinelTable;"
    $sentinelReady = $false
    $restoreDatabaseReady = $false

    try {
        Invoke-ComposeCommand @(
            "exec", "-T", "postgres", "psql", "--username=shijiajing", "--dbname=shijiajing",
            "--command=$sentinelCreateQuery"
        )
        $sentinelReady = $true

        $sourceTableCountText = Invoke-ComposeScalar @(
            "exec", "-T", "postgres", "psql", "--username=shijiajing", "--dbname=shijiajing",
            "--tuples-only", "--no-align", "--command=$tableCountQuery"
        )
        if ($sourceTableCountText -notmatch "^\d+$") {
            throw "PostgreSQL 源库表数量输出无效：$sourceTableCountText"
        }
        $sourceTableCount = [int]$sourceTableCountText

        Invoke-ComposeCommand @(
            "exec", "-T", "postgres", "pg_dump", "--format=custom",
            "--file=$backupPathInContainer", "--username=shijiajing", "--dbname=shijiajing"
        )
        Invoke-ComposeCommand @(
            "exec", "-T", "postgres", "pg_restore", "--list", $backupPathInContainer
        )
        $dumpPath = Join-Path $runEvidenceDir "postgres-container.dump"
        Invoke-ComposeCommand @("cp", "postgres:$backupPathInContainer", $dumpPath)
        $dump = Get-Item -LiteralPath $dumpPath
        if ($dump.Length -le 0) {
            throw "PostgreSQL dump 文件为空：$dumpPath"
        }

        Invoke-ComposeCommand @(
            "exec", "-T", "postgres", "dropdb", "--if-exists", "--username=shijiajing", $restoreDatabase
        )
        Invoke-ComposeCommand @(
            "exec", "-T", "postgres", "createdb", "--username=shijiajing", $restoreDatabase
        )
        $restoreDatabaseReady = $true
        Invoke-ComposeCommand @(
            "exec", "-T", "postgres", "pg_restore", "--exit-on-error",
            "--username=shijiajing", "--dbname=$restoreDatabase", $backupPathInContainer
        )

        $restoredTableCountText = Invoke-ComposeScalar @(
            "exec", "-T", "postgres", "psql", "--username=shijiajing", "--dbname=$restoreDatabase",
            "--tuples-only", "--no-align", "--command=$tableCountQuery"
        )
        if ($restoredTableCountText -notmatch "^\d+$") {
            throw "PostgreSQL 恢复库表数量输出无效：$restoredTableCountText"
        }
        $restoredTableCount = [int]$restoredTableCountText
        if ($restoredTableCount -ne $sourceTableCount) {
            throw "PostgreSQL 恢复库表数量不一致：source=$sourceTableCount，restored=$restoredTableCount"
        }

        $sentinelRowsText = Invoke-ComposeScalar @(
            "exec", "-T", "postgres", "psql", "--username=shijiajing", "--dbname=$restoreDatabase",
            "--tuples-only", "--no-align", "--command=$sentinelCountQuery"
        )
        if ($sentinelRowsText -notmatch "^1$") {
            throw "PostgreSQL 恢复库哨兵数据校验失败：$sentinelRowsText"
        }

        $script:BackupEvidence.status = "passed"
        $script:BackupEvidence.dump = $dumpPath
        $script:BackupEvidence.source_public_table_count = $sourceTableCount
        $script:BackupEvidence.restored_public_table_count = $restoredTableCount
        $script:BackupEvidence.sentinel_rows = [int]$sentinelRowsText
    }
    finally {
        if ($sentinelReady) {
            try {
                Invoke-ComposeCommand @(
                    "exec", "-T", "postgres", "psql", "--username=shijiajing", "--dbname=shijiajing",
                    "--command=$sentinelDropQuery"
                )
            }
            catch {
                Write-Warning "清理 PostgreSQL 备份哨兵表失败：$($_.Exception.Message)"
            }
        }
        if ($restoreDatabaseReady) {
            try {
                Invoke-ComposeCommand @(
                    "exec", "-T", "postgres", "dropdb", "--if-exists", "--username=shijiajing", $restoreDatabase
                )
            }
            catch {
                Write-Warning "清理 PostgreSQL 隔离恢复库失败：$($_.Exception.Message)"
            }
        }
    }
}

try {
    $localPassword = "phase2-local-only"
    $postgresDsn = "postgresql://shijiajing:$localPassword@127.0.0.1:$PostgresPort/shijiajing"

    $env:POSTGRES_PASSWORD = $localPassword
    $env:SHIJIAJING_POSTGRES_PUBLISHED_PORT = $PostgresPort.ToString()
    $env:SHIJIAJING_OTLP_HTTP_PUBLISHED_PORT = $OtlpHttpPort.ToString()
    $env:SHIJIAJING_OTLP_GRPC_PUBLISHED_PORT = $OtlpGrpcPort.ToString()
    $env:SHIJIAJING_TEST_POSTGRES_DSN = $postgresDsn
    $env:SHIJIAJING_REQUIRE_POSTGRES = "1"

    $env:SHIJIAJING_CHECKPOINT_BACKEND = "postgres"
    $env:SHIJIAJING_CHECKPOINT_DSN = $postgresDsn
    $env:SHIJIAJING_GRAPH_PERSISTENCE_MODE = "native"
    $env:SHIJIAJING_REQUEST_LEDGER_BACKEND = "postgres"
    $env:SHIJIAJING_REQUEST_LEDGER_DSN = $postgresDsn
    $env:SHIJIAJING_MEMORY_BACKEND = "postgres"
    $env:SHIJIAJING_MEMORY_DSN = $postgresDsn
    $env:SHIJIAJING_CACHE_BACKEND = "postgres"
    $env:SHIJIAJING_CACHE_DSN = $postgresDsn
    $env:SHIJIAJING_EVENT_STORE_BACKEND = "postgres"
    $env:SHIJIAJING_EVENT_STORE_DSN = $postgresDsn
    $env:SHIJIAJING_TRACE_BACKEND = "opentelemetry"
    $env:SHIJIAJING_TRACE_DSN = "http://127.0.0.1:$OtlpHttpPort/v1/traces"
    if ([string]::IsNullOrWhiteSpace($env:SHIJIAJING_POSTGRES_POOL_MIN_SIZE)) {
        $env:SHIJIAJING_POSTGRES_POOL_MIN_SIZE = "1"
    }
    if ([string]::IsNullOrWhiteSpace($env:SHIJIAJING_POSTGRES_POOL_MAX_SIZE)) {
        $env:SHIJIAJING_POSTGRES_POOL_MAX_SIZE = "4"
    }
    if ([string]::IsNullOrWhiteSpace($env:SHIJIAJING_POSTGRES_POOL_TIMEOUT_SECONDS)) {
        $env:SHIJIAJING_POSTGRES_POOL_TIMEOUT_SECONDS = "30"
    }
    $script:PostgresPoolEvidence = [ordered]@{
        min_size = $env:SHIJIAJING_POSTGRES_POOL_MIN_SIZE
        max_size = $env:SHIJIAJING_POSTGRES_POOL_MAX_SIZE
        timeout_seconds = $env:SHIJIAJING_POSTGRES_POOL_TIMEOUT_SECONDS
    }

    Push-Location $projectRoot
    $locationPushed = $true
    Invoke-ComposeCommand @("up", "-d")
    Wait-HealthyServices -TimeoutSeconds $HealthTimeoutSeconds

    $integrationTestFiles = @(
        "tests/contract/test_native_checkpointers.py",
        "tests/contract/test_request_ledger.py",
        "tests/contract/test_memory_adapters.py",
        "tests/contract/test_cache_adapters.py",
        "tests/contract/test_event_store.py"
    )
    foreach ($integrationTestFile in $integrationTestFiles) {
        Invoke-UvCommand @("run", "pytest", "-q", "-m", "integration", $integrationTestFile)
    }
    Invoke-ComposeCommand @("restart", "postgres")
    Wait-HealthyServices -TimeoutSeconds $HealthTimeoutSeconds
    if ($VerifyBackupRestore) {
        Invoke-BackupRestoreVerification
    }
    Invoke-UvCommand @("run", "shijiajing-preflight", "--storage-only", "--verify-trace", "--json")
    $status = "passed"
    Write-Output "二期 PostgreSQL contract 与 OTLP probe 验证通过"
}
catch {
    $errorMessage = $_.Exception.Message
    $script:BackupEvidence.error = $errorMessage
    throw
}
finally {
    try {
        Invoke-ComposeCommand @("logs", "--no-color")
    }
    catch {
        Write-Warning "读取 Compose 日志失败：$($_.Exception.Message)"
    }
    if (-not $KeepServices) {
        try {
            Invoke-ComposeCommand @("down")
        }
        catch {
            Write-Warning "停止 Compose 服务失败：$($_.Exception.Message)"
        }
    }
    if ($locationPushed) {
        Pop-Location
    }
    foreach ($environmentName in $environmentNames) {
        [Environment]::SetEnvironmentVariable($environmentName, $previousEnvironment[$environmentName])
    }
    if ($transcriptStarted) {
        try {
            Stop-Transcript | Out-Null
        }
        catch {
            Write-Warning "停止 transcript 失败：$($_.Exception.Message)"
        }
    }
    $summary = [ordered]@{
        run_id = $runId
        started_at = $startedAt
        ended_at = (Get-Date).ToUniversalTime().ToString("o")
        status = $status
        error = $errorMessage
        exit_code = if ($status -eq "passed") { 0 } else { 1 }
        transcript = "transcript.log"
        commands = $script:EvidenceCommands.ToArray()
        command_results = $script:EvidenceResults.ToArray()
        health = $script:HealthStatus
        services_kept = [bool]$KeepServices
        postgres_port = $PostgresPort
        otlp_http_port = $OtlpHttpPort
        otlp_grpc_port = $OtlpGrpcPort
        postgres_pool = $script:PostgresPoolEvidence
        backup_restore = $script:BackupEvidence
    }
    try {
        $summaryTempPath = Join-Path $runEvidenceDir ".summary.json.tmp"
        if (Test-Path -LiteralPath $summaryPath) {
            throw "验收 summary 已存在，拒绝覆盖：$summaryPath"
        }
        try {
            $summary | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $summaryTempPath -Encoding utf8
            Move-Item -LiteralPath $summaryTempPath -Destination $summaryPath
        }
        finally {
            if (Test-Path -LiteralPath $summaryTempPath) {
                Remove-Item -LiteralPath $summaryTempPath -Force
            }
        }
    }
    catch {
        Write-Warning "写入验收 summary 失败：$($_.Exception.Message)"
    }
}
