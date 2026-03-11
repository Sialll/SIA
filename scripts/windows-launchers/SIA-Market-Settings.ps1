param()

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $scriptDir "SIA-Common.ps1")

$envFile = Get-SiaEnvFile
Import-SiaShellEnv -EnvFile $envFile | Out-Null

$selectionFile = if ($env:SIA_MARKET_SELECTION_FILE) { $env:SIA_MARKET_SELECTION_FILE } else { Join-Path $HOME ".config\sia-notifier\market-selection.json" }
New-Item -ItemType Directory -Path (Split-Path -Parent $selectionFile) -Force | Out-Null

$currentMarkets = @("US")
if (Test-Path $selectionFile) {
    try {
        $payload = Get-Content $selectionFile -Raw | ConvertFrom-Json
        $enabled = @($payload.enabled_markets | Where-Object { $_ -in @("US", "KR", "EU", "JP") })
        if ($enabled.Count -gt 0) {
            $currentMarkets = $enabled
        }
    } catch {
    }
}

Write-Host ""
Write-Host "SIA 시장 설정"
Write-Host "현재 활성 시장: $($currentMarkets -join ', ')"
Write-Host "가능 코드: US, KR, EU, JP"
$rawInput = Read-Host "활성 시장 코드를 쉼표로 입력하세요 (Enter=현재 유지, 예: US,KR)"

$selectedMarkets = $currentMarkets
if (-not [string]::IsNullOrWhiteSpace($rawInput)) {
    $selectedMarkets = @()
    foreach ($part in $rawInput.Split(",")) {
        $code = $part.Trim().ToUpper()
        if ($code -in @("US", "KR", "EU", "JP") -and $selectedMarkets -notcontains $code) {
            $selectedMarkets += $code
        }
    }
    if ($selectedMarkets.Count -eq 0) {
        $selectedMarkets = @("US")
    }
}

$payload = @{
    enabled_markets = $selectedMarkets
    updated_at      = [DateTimeOffset]::UtcNow.ToString("o")
} | ConvertTo-Json -Depth 3

Set-Content -Path $selectionFile -Value $payload -Encoding UTF8

Write-Host "활성 시장: $($selectedMarkets -join ', ')"
Write-Host "설정 파일: $selectionFile"
Write-Host "참고: TICKERS_KR / TICKERS_EU / TICKERS_JP가 비어 있으면 해당 시장을 켜도 수집 대상은 없습니다."
