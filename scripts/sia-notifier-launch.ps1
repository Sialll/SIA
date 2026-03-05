param()

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoDir = Resolve-Path (Join-Path $scriptDir "..")
$cacheDir = if ($env:XDG_CACHE_HOME) { Join-Path $env:XDG_CACHE_HOME "sia-notifier" } else { Join-Path $env:LOCALAPPDATA "sia-notifier" }
$reportFile = Join-Path $cacheDir "last-run.html"
$runLog = Join-Path $cacheDir "run.log"
$defaultDb = Join-Path $env:USERPROFILE "sia-notifier\trading_signal_notifier.sqlite"
$dbPath = if ($env:SIGNAL_DB_PATH) { $env:SIGNAL_DB_PATH } else { $defaultDb }

New-Item -ItemType Directory -Path $cacheDir -Force | Out-Null
Set-Location $repoDir

python -m sia.trading_signal_notifier --once --db-path $dbPath *> $runLog

$pythonCode = @'
import sqlite3
import sys
from datetime import datetime
from html import escape

html_path, db_path = sys.argv[1], sys.argv[2]
rows = []
error = ""

try:
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT ts, ticker, signal, confidence, sent, COALESCE(error_message, '')
            FROM alerts
            ORDER BY ts DESC
            LIMIT 20
            """
        ).fetchall()
except Exception as exc:
    error = f"DB read error: {exc}"

now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def row(td):
    ts, ticker, signal, confidence, sent, err = td
    try:
        t = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        t = str(ts)
    return (
        f"<tr>"
        f"<td>{escape(str(t))}</td><td>{escape(str(ticker))}</td>"
        f"<td>{escape(str(signal))}</td><td>{float(confidence):.2f}</td>"
        f"<td>{'Y' if sent else 'N'}</td><td>{escape(str(err))}</td></tr>"
    )

with open(html_path, 'w', encoding='utf-8') as f:
    f.write("<!doctype html><html><head><meta charset='utf-8'><title>SIA Notifier Run</title>")
    f.write("<style>body{font-family:Arial,Helvetica,sans-serif;padding:16px;} table{border-collapse:collapse;} th,td{border:1px solid #999;padding:6px 8px;}</style>")
    f.write("</head><body>")
    f.write(f"<h2>SIA Notifier Run</h2><p>time: {escape(now)}</p>")
    if error:
        f.write(f"<p style='color:#cc0000'>{escape(error)}</p>")
    f.write("<table><tr><th>time</th><th>ticker</th><th>signal</th><th>confidence</th><th>sent</th><th>error</th></tr>")
    for each in rows:
        f.write(row(each))
    f.write("</table><p><a href='run.log'>run.log</a></p></body></html>")
'@

$pyPath = Join-Path $env:TEMP "sia_notifier_report.py"
Set-Content -Path $pyPath -Value $pythonCode -Encoding UTF8
python $pyPath $reportFile $dbPath
Remove-Item $pyPath -ErrorAction SilentlyContinue
Start-Process $reportFile
