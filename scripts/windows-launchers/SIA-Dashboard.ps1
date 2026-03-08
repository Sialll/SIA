param()

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $scriptDir "SIA-Common.ps1")

$repoDir = Get-SiaRepoRoot -ScriptRoot $scriptDir
$envFile = Join-Path $HOME ".config\sia-notifier\env"
Import-SiaShellEnv -EnvFile $envFile | Out-Null

$cacheDir = Get-SiaCacheDir
New-Item -ItemType Directory -Path $cacheDir -Force | Out-Null

$dbPath = if ($env:SIGNAL_DB_PATH) { $env:SIGNAL_DB_PATH } else { Join-Path $HOME "sia-notifier\trading_signal_notifier.sqlite" }
$dashboardPath = Join-Path $cacheDir "dashboard.html"

Invoke-SiaPythonScript -RepoDir $repoDir -ScriptPath "src/sia/dashboard_report.py" -Arguments @($dashboardPath, $dbPath)

Start-Process $dashboardPath
Write-Host "대시보드: $dashboardPath"
