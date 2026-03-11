from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path

try:
    from .default_universe import DEFAULT_MARKET_CAP_FLOOR_USD
    from .market_runtime import MARKET_ORDER, load_enabled_markets, selection_file_path
except ImportError:
    from default_universe import DEFAULT_MARKET_CAP_FLOOR_USD  # type: ignore
    from market_runtime import MARKET_ORDER, load_enabled_markets, selection_file_path  # type: ignore


DEFAULT_FULL_UNIVERSE_PROVIDER = os.getenv("SIA_FULL_UNIVERSE_PROVIDER", "manual_json")
DEFAULT_FULL_UNIVERSE_INPUT_PATH = os.path.expanduser(
    os.getenv("SIA_FULL_UNIVERSE_INPUT_PATH", "~/.config/sia-notifier/full-universe-candidates.json")
)
DEFAULT_FULL_UNIVERSE_SNAPSHOT_PATH = os.path.expanduser(
    os.getenv("SIA_FULL_UNIVERSE_SNAPSHOT_PATH", "~/Library/Caches/sia-notifier/full-universe-snapshot.json")
)
DEFAULT_FULL_UNIVERSE_MARKET_CAP_FLOOR_USD = int(
    os.getenv("SIA_FULL_UNIVERSE_MARKET_CAP_FLOOR_USD", str(DEFAULT_MARKET_CAP_FLOOR_USD))
)


@dataclass(frozen=True)
class FullUniverseEntry:
    market: str
    ticker: str
    market_cap_usd: int
    source: str
    company_name: str = ""


def _parse_csv(raw: str | None) -> tuple[str, ...]:
    values = []
    for item in str(raw or "").split(","):
        code = item.strip().upper()
        if code in MARKET_ORDER and code not in values:
            values.append(code)
    return tuple(values)


def _normalize_candidate(item: object, provider: str) -> FullUniverseEntry | None:
    if not isinstance(item, dict):
        return None
    market = str(item.get("market", "")).strip().upper()
    ticker = str(item.get("ticker", "")).strip().upper()
    if market not in MARKET_ORDER or not ticker:
        return None
    try:
        market_cap_usd = int(float(item.get("market_cap_usd", 0)))
    except Exception:
        return None
    if market_cap_usd <= 0:
        return None
    company_name = str(item.get("company_name", "")).strip()
    return FullUniverseEntry(
        market=market,
        ticker=ticker,
        market_cap_usd=market_cap_usd,
        source=provider,
        company_name=company_name,
    )


def _load_manual_json_candidates(path: Path, provider: str) -> tuple[list[FullUniverseEntry], str]:
    if not path.exists():
        return [], "waiting_for_input"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return [], "invalid_input"
    if not isinstance(payload, list):
        return [], "invalid_input"

    entries: list[FullUniverseEntry] = []
    seen: set[tuple[str, str]] = set()
    for item in payload:
        normalized = _normalize_candidate(item, provider)
        if normalized is None:
            continue
        key = (normalized.market, normalized.ticker)
        if key in seen:
            continue
        seen.add(key)
        entries.append(normalized)
    return entries, "ready"


def _load_provider_candidates(provider: str, input_path: Path) -> tuple[list[FullUniverseEntry], str]:
    normalized_provider = str(provider or "").strip().lower() or "manual_json"
    if normalized_provider == "manual_json":
        return _load_manual_json_candidates(input_path, normalized_provider)
    return [], "unsupported_provider"


def collect_full_universe_snapshot(
    *,
    enabled_markets: tuple[str, ...] | None = None,
    provider: str | None = None,
    input_path: str | Path | None = None,
    market_cap_floor_usd: int | None = None,
) -> dict[str, object]:
    markets = enabled_markets or load_enabled_markets(selection_file_path())
    selected_provider = str(provider or DEFAULT_FULL_UNIVERSE_PROVIDER).strip().lower() or "manual_json"
    source_path = Path(str(input_path or DEFAULT_FULL_UNIVERSE_INPUT_PATH)).expanduser()
    floor = int(market_cap_floor_usd or DEFAULT_FULL_UNIVERSE_MARKET_CAP_FLOOR_USD)

    all_candidates, provider_status = _load_provider_candidates(selected_provider, source_path)
    eligible_entries = [
        entry
        for entry in all_candidates
        if entry.market in markets and entry.market_cap_usd >= floor
    ]
    eligible_entries.sort(key=lambda entry: (MARKET_ORDER.index(entry.market), entry.ticker))

    counts_by_market = {
        market: sum(1 for entry in eligible_entries if entry.market == market)
        for market in markets
    }
    candidate_counts_by_market = {
        market: sum(1 for entry in all_candidates if entry.market == market)
        for market in markets
    }

    return {
        "generated_at": int(time.time()),
        "mode": "full_universe_snapshot",
        "enabled_markets": list(markets),
        "provider": selected_provider,
        "provider_status": provider_status,
        "provider_input_path": str(source_path),
        "market_cap_floor_usd": floor,
        "counts": {
            "eligible_total": len(eligible_entries),
            "candidate_total": len(all_candidates),
            "by_market": counts_by_market,
            "candidate_by_market": candidate_counts_by_market,
        },
        "entries": [asdict(entry) for entry in eligible_entries],
        "next_step": (
            "manual_json 입력 대신 실제 market-cap provider를 붙여 daily full-universe refresh로 확장."
        ),
    }


def write_full_universe_snapshot(path: str | Path, snapshot: dict[str, object]) -> Path:
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sia_full_universe_collector")
    parser.add_argument("--provider", default=DEFAULT_FULL_UNIVERSE_PROVIDER)
    parser.add_argument("--input", default=DEFAULT_FULL_UNIVERSE_INPUT_PATH)
    parser.add_argument("--out", default=DEFAULT_FULL_UNIVERSE_SNAPSHOT_PATH)
    parser.add_argument("--market-cap-floor-usd", type=int, default=DEFAULT_FULL_UNIVERSE_MARKET_CAP_FLOOR_USD)
    parser.add_argument("--enabled-markets", default=os.getenv("SIA_ENABLED_MARKETS", ""))
    args = parser.parse_args(argv)

    if str(args.enabled_markets).strip():
        requested = _parse_csv(args.enabled_markets)
        enabled_markets = requested or load_enabled_markets(selection_file_path())
    else:
        enabled_markets = load_enabled_markets(selection_file_path())

    snapshot = collect_full_universe_snapshot(
        enabled_markets=enabled_markets,
        provider=args.provider,
        input_path=args.input,
        market_cap_floor_usd=args.market_cap_floor_usd,
    )
    output_path = write_full_universe_snapshot(args.out, snapshot)
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
