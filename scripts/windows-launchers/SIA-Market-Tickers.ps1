param()

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $scriptDir "SIA-Common.ps1")

$envFile = Get-SiaEnvFile
$scope = Import-SiaShellEnv -EnvFile $envFile

function Read-SiaValue {
    param(
        [string]$Prompt,
        [string]$Current
    )

    $display = if ([string]::IsNullOrWhiteSpace($Current)) { "(비어 있음)" } else { $Current }
    $raw = Read-Host "$Prompt [현재: $display] (Enter=유지, -=비우기)"
    if ([string]::IsNullOrWhiteSpace($raw)) {
        return $Current
    }
    if ($raw.Trim() -eq "-") {
        return ""
    }
    return $raw.Trim()
}

$currentIncludeDefault = if ($env:SIA_INCLUDE_DEFAULT_UNIVERSE) { $env:SIA_INCLUDE_DEFAULT_UNIVERSE } else { "1" }
Write-Host ""
Write-Host "SIA 시장별 티커 설정"
Write-Host "기본 universe 현재값: $currentIncludeDefault (1=포함, 0=제외)"
$includeDefaultRaw = Read-Host "기본 1B+ universe 포함 여부를 입력하세요 (1/0, Enter=유지)"
$includeDefault = $currentIncludeDefault
if (-not [string]::IsNullOrWhiteSpace($includeDefaultRaw)) {
    $normalized = $includeDefaultRaw.Trim()
    if ($normalized -in @("0", "1")) {
        $includeDefault = $normalized
    }
}

$currentUs = if ($env:TICKERS_US) { $env:TICKERS_US } elseif ($env:TICKERS) { $env:TICKERS } else { "" }
$currentKr = if ($env:TICKERS_KR) { $env:TICKERS_KR } else { "" }
$currentEu = if ($env:TICKERS_EU) { $env:TICKERS_EU } else { "" }
$currentJp = if ($env:TICKERS_JP) { $env:TICKERS_JP } else { "" }

$us = Read-SiaValue -Prompt "미국 티커를 쉼표로 입력" -Current $currentUs
$kr = Read-SiaValue -Prompt "한국 티커를 쉼표로 입력" -Current $currentKr
$eu = Read-SiaValue -Prompt "유럽 티커를 쉼표로 입력" -Current $currentEu
$jp = Read-SiaValue -Prompt "일본 티커를 쉼표로 입력" -Current $currentJp

Set-SiaEnvValues -EnvFile $envFile -Values @{
    SIA_INCLUDE_DEFAULT_UNIVERSE = $includeDefault
    TICKERS                      = $us
    TICKERS_US                   = $us
    TICKERS_KR                   = $kr
    TICKERS_EU                   = $eu
    TICKERS_JP                   = $jp
}

Write-Host "저장 완료: $envFile"
if ($includeDefault -eq "1") {
    Write-Host "참고: 입력한 값은 기본 1B+ universe에 추가됩니다."
} else {
    Write-Host "참고: 현재는 기본 1B+ universe를 제외하고 입력 티커만 사용합니다."
}
