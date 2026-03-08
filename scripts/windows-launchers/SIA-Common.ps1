Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-SiaRepoRoot {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ScriptRoot
    )

    return (Resolve-Path (Join-Path $ScriptRoot "..\..")).Path
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
