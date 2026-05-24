param(
    [string]$Query = "hair dryer"
)

$ErrorActionPreference = "Stop"

function Test-EnvValue {
    param([string]$Name)
    -not [string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($Name))
}

$pddConfigured = (Test-EnvValue "PDD_API_ENABLED") -and
    (Test-EnvValue "PDD_CLIENT_ID") -and
    (Test-EnvValue "PDD_CLIENT_SECRET")

$jdConfigured = (Test-EnvValue "JD_API_ENABLED") -and
    (Test-EnvValue "JD_APP_KEY") -and
    (Test-EnvValue "JD_APP_SECRET")

if (-not $pddConfigured -and -not $jdConfigured) {
    Write-Error "No live ecommerce provider is configured. Set PDD_API_ENABLED/PDD_CLIENT_ID/PDD_CLIENT_SECRET or JD_API_ENABLED/JD_APP_KEY/JD_APP_SECRET."
}

$env:ECOMMERCE_API_ENABLED = "true"
$env:ECOMMERCE_LIVE_TEST = "true"
$env:ECOMMERCE_LIVE_QUERY = $Query

$repoRoot = Split-Path -Parent $PSScriptRoot
$backendDir = Join-Path $repoRoot "backend"

Push-Location $backendDir
try {
    mvn -Dtest=LiveOfficialApiSmokeTests test
} finally {
    Pop-Location
}
