param(
    [string]$EnvFile = "",
    [string]$Platforms = "",
    [switch]$Strict,
    [switch]$AsJson
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

function Normalize-Platform {
    param([string]$Value)
    $normalized = $Value.Trim().ToLowerInvariant()
    switch ($normalized) {
        { $_ -in @("pdd", "拼多多", "多多进宝") } { return "pdd" }
        { $_ -in @("jd", "jingdong", "京东", "京东自营") } { return "jd" }
        default { return $normalized }
    }
}

function New-ProviderStatus {
    param(
        [string]$Key,
        [string]$DisplayName,
        [string]$EnableVar,
        [string[]]$RequiredVars,
        [string[]]$RequestedPlatforms,
        [bool]$MasterEnabled
    )
    $missing = New-Object System.Collections.Generic.List[string]
    if (-not $MasterEnabled) {
        $missing.Add("ECOMMERCE_API_ENABLED")
    }
    if (-not (Test-EnvFlag $EnableVar)) {
        $missing.Add($EnableVar)
    }
    foreach ($required in $RequiredVars) {
        if (-not (Test-EnvValue $required)) {
            $missing.Add($required)
        }
    }
    [ordered]@{
        key = $Key
        platform = $DisplayName
        requested = $RequestedPlatforms.Contains($Key)
        enabled = Test-EnvFlag $EnableVar
        configured = $missing.Count -eq 0
        missingConfig = @($missing)
    }
}

Import-DotEnv $EnvFile

$requestedPlatforms = @()
if (-not [string]::IsNullOrWhiteSpace($Platforms)) {
    $requestedPlatforms = $Platforms.Split(",") |
        ForEach-Object { $_.Trim() } |
        Where-Object { $_ } |
        ForEach-Object { Normalize-Platform $_ } |
        Select-Object -Unique
}

$supportedPlatforms = @("pdd", "jd")
$unsupportedPlatforms = @($requestedPlatforms | Where-Object { $supportedPlatforms -notcontains $_ })
$masterEnabled = Test-EnvFlag "ECOMMERCE_API_ENABLED"
$providers = @(
    (New-ProviderStatus "pdd" "拼多多" "PDD_API_ENABLED" @("PDD_CLIENT_ID", "PDD_CLIENT_SECRET") $requestedPlatforms $masterEnabled),
    (New-ProviderStatus "jd" "京东" "JD_API_ENABLED" @("JD_APP_KEY", "JD_APP_SECRET") $requestedPlatforms $masterEnabled)
)

$strictFailures = New-Object System.Collections.Generic.List[string]
foreach ($platform in $unsupportedPlatforms) {
    $strictFailures.Add("Unsupported platform '$platform'. Use pdd or jd.")
}
if ($requestedPlatforms.Count -gt 0) {
    foreach ($platform in $requestedPlatforms | Where-Object { $supportedPlatforms -contains $_ }) {
        $provider = $providers | Where-Object { $_.key -eq $platform } | Select-Object -First 1
        if (-not $provider.configured) {
            $strictFailures.Add("Requested platform '$platform' is not fully configured: $($provider.missingConfig -join ', ').")
        }
    }
} elseif (-not ($providers | Where-Object { $_.configured })) {
    $strictFailures.Add("No official ecommerce provider is fully configured.")
}

$result = [ordered]@{
    envFile = $EnvFile
    envFileFound = Test-Path -LiteralPath $EnvFile
    masterSwitchEnabled = $masterEnabled
    requestedPlatforms = @($requestedPlatforms)
    unsupportedPlatforms = @($unsupportedPlatforms)
    providers = @($providers)
    ready = $strictFailures.Count -eq 0
    strict = $Strict.IsPresent
    failures = @($strictFailures)
}

if ($AsJson.IsPresent) {
    $result | ConvertTo-Json -Depth 6
} else {
    $envState = if ($result.envFileFound) { "found" } else { "not found" }
    Write-Host "Env file: $EnvFile ($envState)"
    Write-Host "ECOMMERCE_API_ENABLED: $(if ($masterEnabled) { 'enabled' } else { 'disabled or missing' })"
    foreach ($provider in $providers) {
        $state = if ($provider.configured) { "configured" } elseif ($provider.enabled) { "incomplete" } else { "disabled or missing" }
        Write-Host "$($provider.platform): $state"
        if ($provider.missingConfig.Count -gt 0) {
            Write-Host "  missing: $($provider.missingConfig -join ', ')"
        }
    }
    if ($unsupportedPlatforms.Count -gt 0) {
        Write-Host "Unsupported requested platforms: $($unsupportedPlatforms -join ', ')"
    }
}

if ($Strict.IsPresent -and $strictFailures.Count -gt 0) {
    Write-Error "Ecommerce config check failed: $($strictFailures -join ' ')"
}
