$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path (Join-Path $ScriptDir "..\..")
$DistDir = Join-Path $ProjectRoot "dist/windows/SIA-Windows"
$DocsDir = Join-Path $DistDir "Docs"
$SupportDir = Join-Path $DistDir ".sia-support"
$SrcDir = Join-Path $SupportDir "src"
$InternalDir = Join-Path $SupportDir "scripts\_internal"

if (Test-Path $DistDir) {
    Remove-Item $DistDir -Recurse -Force
}

New-Item -ItemType Directory -Force -Path $DistDir | Out-Null
New-Item -ItemType Directory -Force -Path $DocsDir | Out-Null
New-Item -ItemType Directory -Force -Path $SupportDir | Out-Null
New-Item -ItemType Directory -Force -Path $SrcDir | Out-Null
New-Item -ItemType Directory -Force -Path $InternalDir | Out-Null

Copy-Item (Join-Path $ProjectRoot "src\*") -Destination $SrcDir -Recurse -Force
Copy-Item (Join-Path $ProjectRoot "scripts\_internal\*") -Destination $InternalDir -Recurse -Force

$launcherFiles = @(
    "SIA.cmd",
    "SIA.ps1",
    "SIA-Run.cmd",
    "SIA-Dashboard.cmd",
    "SIA-Reports.cmd",
    "SIA-Market-Settings.cmd",
    "SIA-Market-Tickers.cmd",
    "SIA-Run.ps1",
    "SIA-Dashboard.ps1",
    "SIA-Reports.ps1",
    "SIA-Market-Settings.ps1",
    "SIA-Market-Tickers.ps1",
    "SIA-Common.ps1"
)

foreach ($file in $launcherFiles) {
    $source = Join-Path $ScriptDir $file
    if (Test-Path $source) {
        Copy-Item $source -Destination $DistDir -Force
    }
}

$commonOverride = @'
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-SiaRepoRoot {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ScriptRoot
    )

    return (Resolve-Path (Join-Path $ScriptRoot ".sia-support")).Path
}

function Get-SiaCacheDir {
    if ($env:XDG_CACHE_HOME) {
        return (Join-Path $env:XDG_CACHE_HOME "sia-notifier")
    }
    if ($env:LOCALAPPDATA) {
        return (Join-Path $env:LOCALAPPDATA "sia-notifier")
    }
    return (Join-Path $HOME "AppData\Local\sia-notifier")
}

function Get-SiaEnvFile {
    return (Join-Path $HOME ".config\sia-notifier\env")
}

function Resolve-SiaEnvValue {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Value,
        [Parameter(Mandatory = $true)]
        [hashtable]$Scope
    )

    $resolved = $Value.Trim()
    if ((($resolved.StartsWith('"')) -and $resolved.EndsWith('"')) -or (($resolved.StartsWith("'")) -and $resolved.EndsWith("'"))) {
        if ($resolved.Length -ge 2) {
            $resolved = $resolved.Substring(1, $resolved.Length - 2)
        }
    }

    $resolved = $resolved.Replace('${HOME}', $HOME).Replace('$HOME', $HOME)

    $resolved = [regex]::Replace(
        $resolved,
        '\$\{([A-Za-z_][A-Za-z0-9_]*)\:\-([^}]*)\}',
        {
            param($match)
            $name = $match.Groups[1].Value
            $fallback = $match.Groups[2].Value
            $existing = ""
            if ($Scope.ContainsKey($name)) {
                $existing = [string]$Scope[$name]
            } elseif (Test-Path "Env:$name") {
                $existing = (Get-Item "Env:$name").Value
            }
            if ([string]::IsNullOrWhiteSpace($existing)) {
                return $fallback
            }
            return $existing
        }
    )

    $resolved = [regex]::Replace(
        $resolved,
        '\$\{([A-Za-z_][A-Za-z0-9_]*)\}',
        {
            param($match)
            $name = $match.Groups[1].Value
            if ($Scope.ContainsKey($name)) {
                return [string]$Scope[$name]
            }
            if (Test-Path "Env:$name") {
                return (Get-Item "Env:$name").Value
            }
            return ""
        }
    )

    return $resolved
}

function Import-SiaShellEnv {
    param(
        [Parameter(Mandatory = $true)]
        [string]$EnvFile
    )

    $scope = @{}
    if (-not (Test-Path $EnvFile)) {
        return $scope
    }

    foreach ($line in Get-Content $EnvFile) {
        $trimmed = $line.Trim()
        if ([string]::IsNullOrWhiteSpace($trimmed) -or $trimmed.StartsWith("#")) {
            continue
        }
        if ($trimmed.StartsWith("export ")) {
            $trimmed = $trimmed.Substring(7).Trim()
        }
        $parts = $trimmed.Split("=", 2)
        if ($parts.Count -ne 2) {
            continue
        }
        $name = $parts[0].Trim()
        if ($name -notmatch '^[A-Za-z_][A-Za-z0-9_]*$') {
            continue
        }
        $resolved = Resolve-SiaEnvValue -Value $parts[1] -Scope $scope
        $scope[$name] = $resolved
        [Environment]::SetEnvironmentVariable($name, $resolved, "Process")
    }

    return $scope
}

function Set-SiaEnvValues {
    param(
        [Parameter(Mandatory = $true)]
        [string]$EnvFile,
        [Parameter(Mandatory = $true)]
        [hashtable]$Values
    )

    $envDir = Split-Path -Parent $EnvFile
    if (-not [string]::IsNullOrWhiteSpace($envDir)) {
        New-Item -ItemType Directory -Path $envDir -Force | Out-Null
    }

    $lines = @()
    if (Test-Path $EnvFile) {
        $lines = Get-Content $EnvFile
    }

    foreach ($key in $Values.Keys) {
        $escaped = [string]$Values[$key]
        $escaped = $escaped.Replace('"', '\"')
        $replacement = 'export {0}="{1}"' -f $key, $escaped
        $pattern = '^export\s+' + [regex]::Escape($key) + '='
        $replaced = $false
        for ($index = 0; $index -lt $lines.Count; $index++) {
            if ($lines[$index] -match $pattern) {
                $lines[$index] = $replacement
                $replaced = $true
                break
            }
        }
        if (-not $replaced) {
            $lines += $replacement
        }
        [Environment]::SetEnvironmentVariable($key, [string]$Values[$key], "Process")
    }

    Set-Content -Path $EnvFile -Value ($lines -join [Environment]::NewLine) -Encoding UTF8
}

function Invoke-SiaPythonScript {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepoDir,
        [Parameter(Mandatory = $true)]
        [string]$ScriptPath,
        [string[]]$Arguments = @()
    )

    $previousPyPath = $env:PYTHONPATH
    $srcDir = Join-Path $RepoDir "src"
    $env:PYTHONPATH = if ([string]::IsNullOrWhiteSpace($previousPyPath)) { $srcDir } else { "$srcDir;$previousPyPath" }

    try {
        $fullScriptPath = Join-Path $RepoDir $ScriptPath
        if (Get-Command python -ErrorAction SilentlyContinue) {
            & python $fullScriptPath @Arguments
            return
        }
        if (Get-Command py -ErrorAction SilentlyContinue) {
            & py -3 $fullScriptPath @Arguments
            return
        }
        throw "python 또는 py 실행 파일을 찾을 수 없습니다."
    } finally {
        if ($null -eq $previousPyPath) {
            Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
        } else {
            $env:PYTHONPATH = $previousPyPath
        }
    }
}
'@

Set-Content -Path (Join-Path $DistDir "SIA-Common.ps1") -Value $commonOverride -Encoding UTF8

$docFiles = @(
    "sales-readiness-checklist.md",
    "sales-ui-ia-plan.md",
    "sales-packaging-flow.md",
    "default-universe.md"
)

foreach ($file in $docFiles) {
    $source = Join-Path $ProjectRoot "docs/$file"
    if (Test-Path $source) {
        Copy-Item $source -Destination $DocsDir -Force
    }
}

@"
SIA Windows release staging

권장 실행:
1. SIA.cmd

보조 실행기:
- SIA-Run.cmd
- SIA-Dashboard.cmd
- SIA-Reports.cmd

문서:
- Docs 폴더 참고

주의:
- 이 폴더는 release staging 산출물이다.
- 현재 Windows staging은 standalone 폴더 기준으로 동작한다.
- 내부 실행 파일은 숨김 폴더(.sia-support)에 포함되어 있으며 사용자가 직접 열 필요가 없다.
"@ | Set-Content -Path (Join-Path $DistDir "README.txt") -Encoding UTF8

Write-Output $DistDir
