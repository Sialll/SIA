param()

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host ""
Write-Host "SIA 실행기"
Write-Host "1. 엔진 실행 (실전)"
Write-Host "2. 엔진 실행 (드라이런)"
Write-Host "3. 대시보드"
Write-Host "4. 리포트"
Write-Host "5. 시장 설정"
Write-Host "6. 시장별 티커 설정"
Write-Host "0. 종료"

$choice = Read-Host "번호를 입력하세요"

switch ($choice) {
    "1" { & (Join-Path $scriptDir "SIA-Run.ps1") -Live }
    "2" { & (Join-Path $scriptDir "SIA-Run.ps1") -DryRun }
    "3" { & (Join-Path $scriptDir "SIA-Dashboard.ps1") }
    "4" { & (Join-Path $scriptDir "SIA-Reports.ps1") }
    "5" { & (Join-Path $scriptDir "SIA-Market-Settings.ps1") }
    "6" { & (Join-Path $scriptDir "SIA-Market-Tickers.ps1") }
    default { exit 0 }
}
