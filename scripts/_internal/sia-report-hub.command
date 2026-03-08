#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CACHE_DIR="${XDG_CACHE_HOME:-$HOME/Library/Caches}/sia-notifier"
REPORT_FILE="${CACHE_DIR}/report-hub.html"

mkdir -p "$CACHE_DIR"

python3 - "$REPORT_FILE" "$CACHE_DIR" <<'PY'
from __future__ import annotations

import datetime as dt
import html
import os
import sys
from pathlib import Path


report_path = Path(sys.argv[1])
cache_dir = Path(sys.argv[2])


def esc(value: object) -> str:
    return html.escape("" if value is None else str(value))


def fmt_ts_from_path(path: Path) -> str:
    if not path.exists():
        return "-"
    return dt.datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")


reports = [
    ("dashboard.html", "메인", "관심 종목 카드, 빠른 추가 진입, 주요 백테스트 바로가기"),
    ("universe-report.html", "관심 종목 구성표", "기본 시총 seed와 사용자 추가 티커를 읽기 쉽게 정리한 리포트"),
    ("universe-snapshot.json", "유니버스 스냅샷", "기본 1B+ seed universe + 사용자 추가 티커 snapshot"),
    ("full-universe-report.html", "시총 상위 종목 보고서", "full universe 후보 수집 축의 provider 입력 / 시총 필터 결과"),
    ("full-universe-snapshot.json", "전종목 유니버스 스냅샷", "full universe 후보 입력을 시장/시총 기준으로 필터링한 snapshot"),
    ("data-quality-report.html", "데이터 품질", "mock 비중, strict 가능률, source 기록 상태 점검"),
    ("backtest-readiness-report.html", "백테스트 준비도", "백테스트 해석 가능 여부와 표본 기준"),
    ("readiness-guard-report.html", "자동 준비도 점검", "준비 구간 임계치 기준 튜닝 비교 갱신 여부"),
    ("price-backtest-report.html", "가격 백테스트", "strict source 기준 horizon 성과"),
    ("position-backtest-report.html", "포지션 백테스트", "중복 포지션 금지 포함 trade 성과"),
    ("factor-breakdown-report.html", "점수 분해", "차트 / 매크로 / 이벤트 / 뉴스 / 종합 방향성"),
    ("tuning-compare.html", "튜닝 비교", "저장된 기준선과 현재 readiness / factor 결과 비교"),
    ("us-open-check-report.html", "미국장 시작 점검", "미국장 시작 직후 관심 종목 반영률을 자동 확인한 결과"),
]

cards = []
for filename, label, description in reports:
    path = cache_dir / filename
    exists = path.exists()
    status = "준비됨" if exists else "없음"
    status_class = "ready" if exists else "missing"
    cards.append(
        f"""
        <article class="card {status_class}">
          <div class="card-head">
            <h2>{esc(label)}</h2>
            <span class="status {status_class}">{status}</span>
          </div>
          <p>{esc(description)}</p>
          <dl class="meta">
            <div><dt>파일</dt><dd>{esc(filename)}</dd></div>
            <div><dt>갱신 시각</dt><dd>{esc(fmt_ts_from_path(path))}</dd></div>
          </dl>
          {"<a class='open-link' href='" + esc(filename) + "' target='_blank' rel='noreferrer'>열기</a>" if exists else "<span class='open-link disabled'>아직 없음</span>"}
        </article>
        """
    )

html_doc = f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>SIA 관리자 체크 포인트</title>
  <style>
    :root {{
      --bg: #f4efe6;
      --panel: rgba(255, 252, 246, 0.88);
      --ink: #171411;
      --muted: #6c6257;
      --line: rgba(23, 20, 17, 0.12);
      --ready: #155e63;
      --missing: #9a3412;
      --shadow: 0 18px 50px rgba(33, 24, 14, 0.10);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      color: var(--ink);
      font-family: "Avenir Next", "Helvetica Neue", Helvetica, Arial, sans-serif;
      background:
        radial-gradient(circle at top left, rgba(21,94,99,0.18), transparent 24%),
        radial-gradient(circle at top right, rgba(198,157,90,0.16), transparent 20%),
        linear-gradient(180deg, #f7f1e8 0%, #efe7db 100%);
      padding: 24px;
    }}
    .shell {{
      width: min(1180px, 100%);
      margin: 0 auto;
    }}
    .hero {{
      padding: 28px;
      margin-bottom: 18px;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 28px;
      box-shadow: var(--shadow);
    }}
    h1 {{
      margin: 0 0 12px;
      font-family: Georgia, "Times New Roman", serif;
      font-size: clamp(34px, 6vw, 72px);
      line-height: 0.95;
      letter-spacing: -0.03em;
    }}
    .hero p {{
      margin: 0;
      color: var(--muted);
      line-height: 1.7;
      max-width: 54rem;
    }}
    .hero-meta {{
      display: flex;
      flex-wrap: wrap;
      gap: 14px;
      margin-top: 14px;
      color: var(--muted);
      font-size: 13px;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 16px;
    }}
    .card {{
      padding: 20px;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 24px;
      box-shadow: var(--shadow);
    }}
    .card-head {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 12px;
      margin-bottom: 10px;
    }}
    .card h2 {{
      margin: 0;
      font-size: 22px;
      letter-spacing: -0.02em;
    }}
    .card p {{
      margin: 0 0 14px;
      color: var(--muted);
      line-height: 1.6;
      font-size: 14px;
    }}
    .status {{
      display: inline-flex;
      align-items: center;
      min-height: 28px;
      padding: 0 10px;
      border-radius: 999px;
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.06em;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.72);
    }}
    .status.ready {{
      color: var(--ready);
      border-color: rgba(21,94,99,0.18);
      background: rgba(21,94,99,0.10);
    }}
    .status.missing {{
      color: var(--missing);
      border-color: rgba(154,52,18,0.18);
      background: rgba(154,52,18,0.10);
    }}
    .meta {{
      margin: 0 0 16px;
      display: grid;
      gap: 8px;
    }}
    .meta div {{
      display: grid;
      gap: 2px;
    }}
    .meta dt {{
      color: var(--muted);
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }}
    .meta dd {{
      margin: 0;
      font-size: 14px;
    }}
    .open-link {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 38px;
      padding: 0 14px;
      border-radius: 999px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.76);
      color: var(--ink);
      text-decoration: none;
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.04em;
    }}
    .open-link.disabled {{
      color: var(--muted);
      pointer-events: none;
    }}
  </style>
</head>
<body>
  <main class="shell">
    <section class="hero">
      <h1>SIA 관리자<br>체크 포인트</h1>
      <p>데이터 품질, 백테스트 준비도, strict 백테스트, 점수 분해, 튜닝 비교처럼 관리자성 리포트를 한곳에 모은 인덱스입니다. 일반 사용자는 메인을 먼저 보고, 세부 점검이 필요할 때 여기로 들어오면 됩니다.</p>
      <div class="hero-meta">
        <span>경로: {esc(cache_dir)}</span>
        <span>생성 시각: {esc(dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))}</span>
      </div>
    </section>
    <section class="grid">
      {''.join(cards)}
    </section>
  </main>
</body>
</html>"""

report_path.write_text(html_doc, encoding="utf-8")
print(report_path)
PY

if [[ "${SIA_NO_OPEN_REPORT_HUB:-0}" != "1" ]] && command -v open >/dev/null 2>&1; then
  open "$REPORT_FILE" >/dev/null 2>&1 || true
fi

echo "리포트 허브: $REPORT_FILE"
