param(
    [string]$Query = "hair dryer",
    [string]$Platforms = ""
)

$ErrorActionPreference = "Stop"

function Test-EnvValue {
    param([string]$Name)
    -not [string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($Name))
}

function Test-EnvFlag {
    param([string]$Name)
    $value = [Environment]::GetEnvironmentVariable($Name)
    if ([string]::IsNullOrWhiteSpace($value)) {
        return $false
    }
    $normalized = $value.Trim().ToLowerInvariant()
    @("1", "true", "yes", "on").Contains($normalized)
}

$pddConfigured = (Test-EnvFlag "PDD_API_ENABLED") -and
    (Test-EnvValue "PDD_CLIENT_ID") -and
    (Test-EnvValue "PDD_CLIENT_SECRET")

$jdConfigured = (Test-EnvFlag "JD_API_ENABLED") -and
    (Test-EnvValue "JD_APP_KEY") -and
    (Test-EnvValue "JD_APP_SECRET")

$requestedPlatforms = @()
if (-not [string]::IsNullOrWhiteSpace($Platforms)) {
    $requestedPlatforms = $Platforms.Split(",") | ForEach-Object { $_.Trim().ToLowerInvariant() } | Where-Object { $_ }
}

foreach ($platform in $requestedPlatforms) {
    if ($platform -ne "pdd" -and $platform -ne "jd" -and $platform -ne "jingdong") {
        Write-Error "Unsupported platform '$platform'. Use pdd or jd."
    }
    if ($platform -eq "pdd" -and -not $pddConfigured) {
        Write-Error "PDD was requested but PDD_API_ENABLED=true/PDD_CLIENT_ID/PDD_CLIENT_SECRET is not fully configured."
    }
    if (($platform -eq "jd" -or $platform -eq "jingdong") -and -not $jdConfigured) {
        Write-Error "JD was requested but JD_API_ENABLED=true/JD_APP_KEY/JD_APP_SECRET is not fully configured."
    }
}

if (-not $pddConfigured -and -not $jdConfigured) {
    Write-Error "No live ecommerce provider is configured. Set PDD_API_ENABLED=true/PDD_CLIENT_ID/PDD_CLIENT_SECRET or JD_API_ENABLED=true/JD_APP_KEY/JD_APP_SECRET."
}

$env:ECOMMERCE_API_ENABLED = "true"
$env:ECOMMERCE_LIVE_TEST = "true"
$env:ECOMMERCE_LIVE_QUERY = $Query
if ($requestedPlatforms.Count -gt 0) {
    $env:ECOMMERCE_LIVE_PLATFORMS = ($requestedPlatforms -join ",")
} else {
    $env:ECOMMERCE_LIVE_PLATFORMS = ""
}

$repoRoot = Split-Path -Parent $PSScriptRoot
$backendDir = Join-Path $repoRoot "backend"

Push-Location $backendDir
try {
    mvn -Dtest=LiveOfficialApiSmokeTests test
} finally {
    Pop-Location
}
