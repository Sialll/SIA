param(
    [ValidateSet("balanced", "conservative", "aggressive")]
    [string]$Mode = "balanced",
    [switch]$DryRun,
    [switch]$Live
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $scriptDir "SIA-Common.ps1")

if ($DryRun.IsPresent -and $Live.IsPresent) {
    throw "-DryRun 과 -Live 는 동시에 사용할 수 없습니다."
}

$repoDir = Get-SiaRepoRoot -ScriptRoot $scriptDir
$envFile = Join-Path $HOME ".config\sia-notifier\env"
Import-SiaShellEnv -EnvFile $envFile | Out-Null

$cacheDir = Get-SiaCacheDir
New-Item -ItemType Directory -Path $cacheDir -Force | Out-Null

switch ($Mode) {
    "conservative" {
        $env:SIGNAL_TREND_WEIGHT = "0.6"
        $env:SIGNAL_RSI_WEIGHT = "0.2"
        $env:SIGNAL_NEWS_WEIGHT = "0.2"
        $env:SIGNAL_THRESHOLD = "45"
    }
    "aggressive" {
        $env:SIGNAL_TREND_WEIGHT = "0.45"
        $env:SIGNAL_RSI_WEIGHT = "0.25"
        $env:SIGNAL_NEWS_WEIGHT = "0.30"
        $env:SIGNAL_THRESHOLD = "25"
    }
    default {
        $env:SIGNAL_TREND_WEIGHT = "0.55"
        $env:SIGNAL_RSI_WEIGHT = "0.25"
        $env:SIGNAL_NEWS_WEIGHT = "0.20"
        $env:SIGNAL_THRESHOLD = "35"
    }
}

if ($DryRun.IsPresent) {
    $env:SIA_DRY_RUN = "1"
} elseif ($Live.IsPresent) {
    $env:SIA_DRY_RUN = "0"
}

$dbPath = if ($env:SIGNAL_DB_PATH) { $env:SIGNAL_DB_PATH } else { Join-Path $HOME "sia-notifier\trading_signal_notifier.sqlite" }
$dashboardPath = Join-Path $cacheDir "dashboard.html"

Invoke-SiaPythonScript -RepoDir $repoDir -ScriptPath "src/sia/trading_signal_notifier.py" -Arguments @("--once", "--db-path", $dbPath)
Invoke-SiaPythonScript -RepoDir $repoDir -ScriptPath "src/sia/dashboard_report.py" -Arguments @($dashboardPath, $dbPath)

Start-Process $dashboardPath
Write-Host "대시보드: $dashboardPath"
