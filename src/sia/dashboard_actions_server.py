from __future__ import annotations

import argparse
import json
import os
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


PROJECT_ROOT = Path(__file__).resolve().parents[2]
INTERNAL_SCRIPTS = PROJECT_ROOT / "scripts" / "_internal"
CACHE_DIR = Path(os.path.expanduser(os.getenv("XDG_CACHE_HOME", "~/Library/Caches"))) / "sia-notifier"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
BACKGROUND_LOG = CACHE_DIR / "dashboard-actions-background.log"


def run_script(args: list[str], env_overrides: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{PROJECT_ROOT / 'src'}{':' + env['PYTHONPATH'] if env.get('PYTHONPATH') else ''}"
    if env_overrides:
        env.update(env_overrides)
    return subprocess.run(
        args,
        cwd=str(PROJECT_ROOT),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def spawn_background(args: list[str], env_overrides: dict[str, str] | None = None) -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{PROJECT_ROOT / 'src'}{':' + env['PYTHONPATH'] if env.get('PYTHONPATH') else ''}"
    if env_overrides:
        env.update(env_overrides)
    log_fp = BACKGROUND_LOG.open("a", encoding="utf-8")
    subprocess.Popen(
        args,
        cwd=str(PROJECT_ROOT),
        env=env,
        stdout=log_fp,
        stderr=log_fp,
        start_new_session=True,
    )


class Handler(BaseHTTPRequestHandler):
    server_version = "SIAActions/1.0"

    def _send_json(self, status: int, payload: dict[str, object]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> str:
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            content_length = 0
        if content_length <= 0:
            return ""
        return self.rfile.read(content_length).decode("utf-8", errors="ignore")

    def do_OPTIONS(self) -> None:
        self._send_json(200, {"ok": True})

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._send_json(200, {"ok": True, "service": "dashboard-actions"})
            return
        self._send_json(404, {"ok": False, "error": "not_found"})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        body = self._read_body().strip()

        if parsed.path == "/api/tickers/quick-add":
            if not body:
                self._send_json(400, {"ok": False, "error": "empty_input"})
                return
            result = run_script(
                ["bash", str(INTERNAL_SCRIPTS / "sia-market-tickers.command"), "--quick-add", body],
                {"SIA_NO_OPEN_DASHBOARD": "1"},
            )
            if result.returncode != 0:
                self._send_json(
                    500,
                    {"ok": False, "error": "quick_add_failed", "stdout": result.stdout, "stderr": result.stderr},
                )
                return
            run_script(["bash", str(INTERNAL_SCRIPTS / "sia-universe-refresh.command")], {"SIA_NO_OPEN_UNIVERSE_REPORT": "1"})
            run_script(["bash", str(INTERNAL_SCRIPTS / "sia-dashboard.command")], {"SIA_NO_OPEN_DASHBOARD": "1"})
            run_script(["bash", str(INTERNAL_SCRIPTS / "sia-report-hub.command")], {"SIA_NO_OPEN_REPORT_HUB": "1"})
            self._send_json(200, {"ok": True, "message": "관심 종목을 추가했고 메인을 다시 만들었습니다.", "stdout": result.stdout})
            return

        if parsed.path == "/api/tickers/quick-remove":
            if not body:
                self._send_json(400, {"ok": False, "error": "empty_input"})
                return
            result = run_script(
                ["bash", str(INTERNAL_SCRIPTS / "sia-market-tickers.command"), "--quick-remove", body],
                {"SIA_NO_OPEN_DASHBOARD": "1"},
            )
            if result.returncode != 0:
                self._send_json(
                    500,
                    {"ok": False, "error": "quick_remove_failed", "stdout": result.stdout, "stderr": result.stderr},
                )
                return
            run_script(["bash", str(INTERNAL_SCRIPTS / "sia-universe-refresh.command")], {"SIA_NO_OPEN_UNIVERSE_REPORT": "1"})
            run_script(["bash", str(INTERNAL_SCRIPTS / "sia-dashboard.command")], {"SIA_NO_OPEN_DASHBOARD": "1"})
            run_script(["bash", str(INTERNAL_SCRIPTS / "sia-report-hub.command")], {"SIA_NO_OPEN_REPORT_HUB": "1"})
            self._send_json(200, {"ok": True, "message": "관심 종목을 삭제했고 메인을 다시 만들었습니다.", "stdout": result.stdout})
            return

        if parsed.path == "/api/tickers/bulk-set":
            if not body:
                self._send_json(400, {"ok": False, "error": "empty_input"})
                return
            try:
                payload = json.loads(body)
            except json.JSONDecodeError:
                self._send_json(400, {"ok": False, "error": "invalid_json", "message": "일괄 붙여넣기 형식이 올바르지 않습니다."})
                return

            market = str(payload.get("market", "")).upper().strip()
            tickers = str(payload.get("tickers", "")).strip()
            market_label = {
                "US": "미국",
                "KR": "한국",
                "EU": "유럽",
                "JP": "일본",
            }.get(market, market)
            if market not in {"US", "KR", "EU", "JP"}:
                self._send_json(400, {"ok": False, "error": "invalid_market", "message": "시장 선택값이 올바르지 않습니다."})
                return

            result = run_script(
                ["bash", str(INTERNAL_SCRIPTS / "sia-market-tickers.command"), "--bulk-set", market, tickers],
                {"SIA_NO_OPEN_DASHBOARD": "1"},
            )
            if result.returncode != 0:
                self._send_json(
                    500,
                    {"ok": False, "error": "bulk_set_failed", "stdout": result.stdout, "stderr": result.stderr},
                )
                return
            run_script(["bash", str(INTERNAL_SCRIPTS / "sia-universe-refresh.command")], {"SIA_NO_OPEN_UNIVERSE_REPORT": "1"})
            run_script(["bash", str(INTERNAL_SCRIPTS / "sia-dashboard.command")], {"SIA_NO_OPEN_DASHBOARD": "1"})
            run_script(["bash", str(INTERNAL_SCRIPTS / "sia-report-hub.command")], {"SIA_NO_OPEN_REPORT_HUB": "1"})
            self._send_json(
                200,
                {
                    "ok": True,
                    "message": f"{market_label} 시장 티커 목록을 일괄 반영했고 메인을 다시 만들었습니다.",
                    "stdout": result.stdout,
                },
            )
            return

        if parsed.path == "/api/run-live-once":
            result = run_script(
                ["bash", str(INTERNAL_SCRIPTS / "sia-notifier-launch.command"), "balanced", "--live"],
                {"SIA_NO_OPEN_DASHBOARD": "1", "SIA_NO_OPEN_LAST_RUN": "1"},
            )
            status = 200 if result.returncode == 0 else 500
            self._send_json(
                status,
                {
                    "ok": result.returncode == 0,
                    "message": "엔진 1회 실행이 끝났습니다." if result.returncode == 0 else "엔진 1회 실행에 실패했습니다.",
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                },
            )
            return

        if parsed.path == "/api/backtest-refresh":
            spawn_background(
                ["bash", str(INTERNAL_SCRIPTS / "sia-backtest-refresh.command")],
                {"SIA_NO_OPEN_BACKTEST_REFRESH": "1", "SIA_NO_OPEN_DASHBOARD": "1", "SIA_NO_OPEN_REPORT_HUB": "1"},
            )
            self._send_json(202, {"ok": True, "message": "백테스트 갱신을 시작했습니다. 잠시 뒤 관리자 체크 포인트에서 확인하세요."})
            return

        if parsed.path == "/api/dashboard-refresh":
            result = run_script(["bash", str(INTERNAL_SCRIPTS / "sia-dashboard.command")], {"SIA_NO_OPEN_DASHBOARD": "1"})
            if result.returncode != 0:
                self._send_json(500, {"ok": False, "error": "dashboard_refresh_failed", "stdout": result.stdout, "stderr": result.stderr})
                return
            self._send_json(200, {"ok": True, "message": "메인을 다시 만들었습니다.", "stdout": result.stdout})
            return

        self._send_json(404, {"ok": False, "error": "not_found"})

    def log_message(self, format: str, *args: object) -> None:
        return


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=int(os.getenv("SIA_DASHBOARD_ACTIONS_PORT", "8765")))
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
