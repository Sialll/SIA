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
$universeSnapshotPath = if ($env:SIA_UNIVERSE_SNAPSHOT_PATH) { $env:SIA_UNIVERSE_SNAPSHOT_PATH } else { Join-Path $cacheDir "universe-snapshot.json" }
$universeReportPath = if ($env:SIA_UNIVERSE_REPORT_PATH) { $env:SIA_UNIVERSE_REPORT_PATH } else { Join-Path $cacheDir "universe-report.html" }
$fullUniverseSnapshotPath = if ($env:SIA_FULL_UNIVERSE_SNAPSHOT_PATH) { $env:SIA_FULL_UNIVERSE_SNAPSHOT_PATH } else { Join-Path $cacheDir "full-universe-snapshot.json" }
$fullUniverseReportPath = if ($env:SIA_FULL_UNIVERSE_REPORT_PATH) { $env:SIA_FULL_UNIVERSE_REPORT_PATH } else { Join-Path $cacheDir "full-universe-report.html" }
$fullUniverseInputPath = if ($env:SIA_FULL_UNIVERSE_INPUT_PATH) { $env:SIA_FULL_UNIVERSE_INPUT_PATH } else { Join-Path $HOME ".config\sia-notifier\full-universe-candidates.json" }
$fullUniverseProvider = if ($env:SIA_FULL_UNIVERSE_PROVIDER) { $env:SIA_FULL_UNIVERSE_PROVIDER } else { "manual_json" }
$fullUniverseFloor = if ($env:SIA_FULL_UNIVERSE_MARKET_CAP_FLOOR_USD) { $env:SIA_FULL_UNIVERSE_MARKET_CAP_FLOOR_USD } else { "1000000000" }
$reportHubPath = Join-Path $cacheDir "report-hub.html"

Invoke-SiaPythonScript -RepoDir $repoDir -ScriptPath "src/sia/dashboard_report.py" -Arguments @($dashboardPath, $dbPath)
Invoke-SiaPythonScript -RepoDir $repoDir -ScriptPath "src/sia/universe_collector.py" -Arguments @("--out", $universeSnapshotPath)
Invoke-SiaPythonScript -RepoDir $repoDir -ScriptPath "src/sia/universe_report.py" -Arguments @("--snapshot", $universeSnapshotPath, "--out", $universeReportPath)
Invoke-SiaPythonScript -RepoDir $repoDir -ScriptPath "src/sia/full_universe_collector.py" -Arguments @("--provider", $fullUniverseProvider, "--input", $fullUniverseInputPath, "--out", $fullUniverseSnapshotPath, "--market-cap-floor-usd", $fullUniverseFloor)
Invoke-SiaPythonScript -RepoDir $repoDir -ScriptPath "src/sia/full_universe_report.py" -Arguments @("--snapshot", $fullUniverseSnapshotPath, "--out", $fullUniverseReportPath)

$reports = @(
    @{ File = "dashboard.html"; Label = "대시보드"; Description = "운영 카드 / 필터 / 상세 패널" },
    @{ File = "universe-report.html"; Label = "유니버스 리포트"; Description = "기본 1B+ seed universe와 사용자 추가 티커 리포트" },
    @{ File = "universe-snapshot.json"; Label = "유니버스 스냅샷"; Description = "기본 1B+ seed universe + 사용자 추가 티커 snapshot" },
    @{ File = "full-universe-report.html"; Label = "전종목 유니버스 리포트"; Description = "full universe 후보 수집 축의 provider 입력 / 시총 필터 결과" },
    @{ File = "full-universe-snapshot.json"; Label = "전종목 유니버스 스냅샷"; Description = "full universe 후보 입력을 시장/시총 기준으로 필터링한 snapshot" }
)

$cards = foreach ($report in $reports) {
    $path = Join-Path $cacheDir $report.File
    $exists = Test-Path $path
    $status = if ($exists) { "준비됨" } else { "없음" }
    $statusClass = if ($exists) { "ready" } else { "missing" }
    $updatedAt = if ($exists) { (Get-Item $path).LastWriteTime.ToString("yyyy-MM-dd HH:mm:ss") } else { "-" }
    $openHtml = if ($exists) {
        "<a class='open-link' href='" + $report.File + "' target='_blank' rel='noreferrer'>열기</a>"
    } else {
        "<span class='open-link disabled'>아직 없음</span>"
    }

@"
        <article class="card $statusClass">
          <div class="card-head">
            <h2>$($report.Label)</h2>
            <span class="status $statusClass">$status</span>
          </div>
          <p>$($report.Description)</p>
          <dl class="meta">
            <div><dt>파일</dt><dd>$($report.File)</dd></div>
            <div><dt>갱신 시각</dt><dd>$updatedAt</dd></div>
          </dl>
          $openHtml
        </article>
"@
}

$html = @"
<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>SIA 리포트 허브 (Windows)</title>
  <style>
    :root {
      --bg: #f4efe6;
      --panel: rgba(255,252,246,0.88);
      --ink: #171411;
      --muted: #6c6257;
      --line: rgba(23,20,17,0.12);
      --ready: #155e63;
      --missing: #9a3412;
      --shadow: 0 18px 50px rgba(33,24,14,0.10);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      color: var(--ink);
      font-family: "Segoe UI", "Noto Sans KR", sans-serif;
      background:
        radial-gradient(circle at top left, rgba(21,94,99,0.18), transparent 24%),
        linear-gradient(180deg, #f7f1e8 0%, #efe7db 100%);
      padding: 24px;
    }
    .shell { width: min(1180px, 100%); margin: 0 auto; }
    .hero, .card {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 24px;
      box-shadow: var(--shadow);
    }
    .hero { padding: 28px; margin-bottom: 18px; }
    .hero h1 { margin: 0 0 12px; font-size: clamp(34px, 6vw, 64px); line-height: 0.95; }
    .hero p { margin: 0; color: var(--muted); line-height: 1.7; max-width: 54rem; }
    .hero-meta { display: flex; flex-wrap: wrap; gap: 14px; margin-top: 14px; color: var(--muted); font-size: 13px; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 16px; }
    .card { padding: 20px; }
    .card-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; margin-bottom: 10px; }
    .card h2 { margin: 0; font-size: 22px; }
    .card p { margin: 0 0 14px; color: var(--muted); line-height: 1.6; font-size: 14px; }
    .status, .open-link {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 28px;
      padding: 0 10px;
      border-radius: 999px;
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.06em;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.72);
    }
    .status.ready { color: var(--ready); border-color: rgba(21,94,99,0.18); background: rgba(21,94,99,0.10); }
    .status.missing { color: var(--missing); border-color: rgba(154,52,18,0.18); background: rgba(154,52,18,0.10); }
    .meta { margin: 0 0 16px; display: grid; gap: 8px; }
    .meta div { display: grid; gap: 2px; }
    .meta dt { color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em; }
    .meta dd { margin: 0; font-size: 14px; }
    .open-link { min-height: 38px; padding: 0 14px; color: var(--ink); text-decoration: none; font-size: 12px; letter-spacing: 0.04em; }
    .open-link.disabled { color: var(--muted); pointer-events: none; }
  </style>
</head>
<body>
  <main class="shell">
    <section class="hero">
      <h1>SIA<br>리포트 허브</h1>
      <p>Windows 백업 실행기 기준으로 생성한 핵심 리포트 모음입니다.</p>
      <div class="hero-meta">
        <span>생성 시각: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")</span>
        <span>캐시 경로: $cacheDir</span>
      </div>
    </section>
    <section class="grid">
      $($cards -join "`n")
    </section>
  </main>
</body>
</html>
"@

Set-Content -Path $reportHubPath -Value $html -Encoding UTF8
Start-Process $reportHubPath
Write-Host "리포트 허브: $reportHubPath"
