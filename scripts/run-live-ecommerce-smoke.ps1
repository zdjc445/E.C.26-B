param(
    [string]$Query = "hair dryer",
    [string]$Platforms = "",
    [string]$EnvFile = "",
    [string]$MinPrice = "",
    [string]$MaxPrice = "",
    [string]$SortBy = "",
    [switch]$WithCoupon,
    [switch]$OfficialOnly,
    [switch]$SelfOperatedOnly,
    [string]$ReportPath = ""
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($EnvFile)) {
    $EnvFile = Join-Path $repoRoot ".env"
}

function Import-DotEnv {
    param([string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path) -or -not (Test-Path -LiteralPath $Path)) {
        return
    }
    foreach ($rawLine in Get-Content -LiteralPath $Path) {
        $line = $rawLine.Trim()
        if ([string]::IsNullOrWhiteSpace($line) -or $line.StartsWith("#")) {
            continue
        }
        if ($line.StartsWith("export ")) {
            $line = $line.Substring(7).Trim()
        }
        $separator = $line.IndexOf("=")
        if ($separator -le 0) {
            continue
        }
        $name = $line.Substring(0, $separator).Trim()
        if ($name -notmatch "^[A-Za-z_][A-Za-z0-9_]*$") {
            continue
        }
        if (-not [string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($name))) {
            continue
        }
        $value = $line.Substring($separator + 1).Trim()
        if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        [Environment]::SetEnvironmentVariable($name, $value, "Process")
    }
}

Import-DotEnv $EnvFile

function Test-EnvValue {
    param([string]$Name)
    $value = [Environment]::GetEnvironmentVariable($Name)
    if ([string]::IsNullOrWhiteSpace($value)) {
        return $false
    }
    $normalized = $value.Trim().ToLowerInvariant()
    if ($normalized.StartsWith("<") -and $normalized.EndsWith(">")) {
        return $false
    }
    if ($normalized.Contains("your-") -or $normalized.Contains("replace-")) {
        return $false
    }
    -not @("...", "xxx", "todo", "tbd", "placeholder", "change-me", "changeme", "change_me").Contains($normalized)
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

$allowedSortModes = @("comprehensive", "price_asc", "sales_desc", "rating_desc")
$effectiveSortBy = $SortBy
if ([string]::IsNullOrWhiteSpace($effectiveSortBy)) {
    $effectiveSortBy = [Environment]::GetEnvironmentVariable("ECOMMERCE_LIVE_SORT_BY")
}
if ([string]::IsNullOrWhiteSpace($effectiveSortBy)) {
    $effectiveSortBy = "price_asc"
}
$effectiveSortBy = $effectiveSortBy.Trim().ToLowerInvariant()
if (-not $allowedSortModes.Contains($effectiveSortBy)) {
    Write-Error "Unsupported sortBy '$effectiveSortBy'. Use comprehensive, price_asc, sales_desc, or rating_desc."
}

$env:ECOMMERCE_API_ENABLED = "true"
$env:ECOMMERCE_LIVE_TEST = "true"
$env:ECOMMERCE_LIVE_QUERY = $Query
$env:ECOMMERCE_LIVE_SORT_BY = $effectiveSortBy
if (-not [string]::IsNullOrWhiteSpace($MinPrice)) {
    $env:ECOMMERCE_LIVE_MIN_PRICE = $MinPrice
}
if (-not [string]::IsNullOrWhiteSpace($MaxPrice)) {
    $env:ECOMMERCE_LIVE_MAX_PRICE = $MaxPrice
}
if ($WithCoupon.IsPresent -or (Test-EnvFlag "ECOMMERCE_LIVE_WITH_COUPON")) {
    $env:ECOMMERCE_LIVE_WITH_COUPON = "true"
}
if ($OfficialOnly.IsPresent -or (Test-EnvFlag "ECOMMERCE_LIVE_OFFICIAL_ONLY")) {
    $env:ECOMMERCE_LIVE_OFFICIAL_ONLY = "true"
}
if ($SelfOperatedOnly.IsPresent -or (Test-EnvFlag "ECOMMERCE_LIVE_SELF_OPERATED_ONLY")) {
    $env:ECOMMERCE_LIVE_SELF_OPERATED_ONLY = "true"
}
if ($requestedPlatforms.Count -gt 0) {
    $env:ECOMMERCE_LIVE_PLATFORMS = ($requestedPlatforms -join ",")
} else {
    $env:ECOMMERCE_LIVE_PLATFORMS = ""
}

$backendDir = Join-Path $repoRoot "backend"
if ([string]::IsNullOrWhiteSpace($ReportPath)) {
    $ReportPath = [Environment]::GetEnvironmentVariable("ECOMMERCE_LIVE_REPORT_PATH")
}
if ([string]::IsNullOrWhiteSpace($ReportPath)) {
    $ReportPath = Join-Path $backendDir "target\live-ecommerce-smoke-report.json"
}
if (-not [System.IO.Path]::IsPathRooted($ReportPath)) {
    $ReportPath = [System.IO.Path]::GetFullPath((Join-Path $repoRoot $ReportPath))
}
$env:ECOMMERCE_LIVE_REPORT_PATH = $ReportPath

Push-Location $backendDir
try {
    mvn -Dtest=LiveOfficialApiSmokeTests test
} finally {
    Pop-Location
}

if (Test-Path -LiteralPath $ReportPath) {
    Write-Host "Live ecommerce smoke report: $ReportPath"
}
