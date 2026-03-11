from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path

try:
    from .default_universe import (
        DEFAULT_MARKET_CAP_FLOOR_USD,
        default_market_tickers,
        use_default_universe,
    )
    from .market_runtime import MARKET_ORDER, MARKET_TICKER_ENV, load_enabled_markets, selection_file_path
except ImportError:
    from default_universe import (  # type: ignore
        DEFAULT_MARKET_CAP_FLOOR_USD,
        default_market_tickers,
        use_default_universe,
    )
    from market_runtime import MARKET_ORDER, MARKET_TICKER_ENV, load_enabled_markets, selection_file_path  # type: ignore


DEFAULT_UNIVERSE_SNAPSHOT_PATH = os.path.expanduser(
    os.getenv("SIA_UNIVERSE_SNAPSHOT_PATH", "~/Library/Caches/sia-notifier/universe-snapshot.json")
)
DEFAULT_UNIVERSE_HISTORY_PATH = os.path.expanduser(
    os.getenv("SIA_UNIVERSE_HISTORY_PATH", "~/Library/Caches/sia-notifier/universe-history.jsonl")
)


@dataclass(frozen=True)
class UniverseEntry:
    market: str
    ticker: str
    source: str
    market_cap_floor_usd: int


def _parse_csv(raw: str | None) -> list[str]:
    return [item.strip().upper() for item in str(raw or "").split(",") if item.strip()]


def _bool_value(raw: str | None, default: bool) -> bool:
    normalized = str(raw or "").strip().lower()
    if normalized == "":
        return default
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _env_market_tickers(market: str) -> list[str]:
    env_name = MARKET_TICKER_ENV[market]
    raw_value = os.getenv(env_name)
    if market == "US" and (raw_value is None or raw_value.strip() == ""):
        raw_value = os.getenv("TICKERS", "")
    return _parse_csv(raw_value)


def _dedupe_entries(entries: list[UniverseEntry]) -> list[UniverseEntry]:
    seen: set[tuple[str, str]] = set()
    deduped: list[UniverseEntry] = []
    for entry in entries:
        key = (entry.market, entry.ticker)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(entry)
    return deduped


def collect_seed_universe_snapshot(
    *,
    enabled_markets: tuple[str, ...] | None = None,
    include_default_universe: bool | None = None,
) -> dict[str, object]:
    markets = enabled_markets or load_enabled_markets(selection_file_path())
    include_default = use_default_universe() if include_default_universe is None else bool(include_default_universe)

    entries: list[UniverseEntry] = []
    for market in MARKET_ORDER:
        if market not in markets:
            continue
        if include_default:
            for ticker in default_market_tickers(market):
                entries.append(
                    UniverseEntry(
                        market=market,
                        ticker=ticker,
                        source="default_seed",
                        market_cap_floor_usd=DEFAULT_MARKET_CAP_FLOOR_USD,
                    )
                )
        for ticker in _env_market_tickers(market):
            entries.append(
                UniverseEntry(
                    market=market,
                    ticker=ticker,
                    source="user",
                    market_cap_floor_usd=DEFAULT_MARKET_CAP_FLOOR_USD,
                )
            )

    deduped = _dedupe_entries(entries)
    per_market_counts = {
        market: sum(1 for entry in deduped if entry.market == market)
        for market in markets
    }
    per_source_counts = {
        "default_seed": sum(1 for entry in deduped if entry.source == "default_seed"),
        "user": sum(1 for entry in deduped if entry.source == "user"),
    }

    return {
        "generated_at": int(time.time()),
        "enabled_markets": list(markets),
        "include_default_universe": include_default,
        "market_cap_floor_usd": DEFAULT_MARKET_CAP_FLOOR_USD,
        "mode": "seed_universe_snapshot",
        "future_collector_status": "skeleton_only",
        "future_collector_next_step": "Attach market-cap data provider and daily full-universe refresh job.",
        "counts": {
            "total": len(deduped),
            "by_market": per_market_counts,
            "by_source": per_source_counts,
        },
        "entries": [asdict(entry) for entry in deduped],
    }


def write_universe_snapshot(path: str | Path, snapshot: dict[str, object]) -> Path:
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def append_universe_history(path: str | Path, snapshot: dict[str, object]) -> Path:
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    history_record = {
        "generated_at": snapshot.get("generated_at"),
        "enabled_markets": snapshot.get("enabled_markets"),
        "include_default_universe": snapshot.get("include_default_universe"),
        "market_cap_floor_usd": snapshot.get("market_cap_floor_usd"),
        "counts": snapshot.get("counts"),
    }
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(history_record, ensure_ascii=False) + "\n")
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sia_universe_collector")
    parser.add_argument("--out", default=DEFAULT_UNIVERSE_SNAPSHOT_PATH)
    parser.add_argument("--history-out", default=DEFAULT_UNIVERSE_HISTORY_PATH)
    parser.add_argument("--enabled-markets", default=os.getenv("SIA_ENABLED_MARKETS", ""))
    parser.add_argument("--include-default-universe", default=os.getenv("SIA_INCLUDE_DEFAULT_UNIVERSE", "1"))
    args = parser.parse_args(argv)

    if str(args.enabled_markets).strip():
        requested = tuple(
            market.strip().upper()
            for market in str(args.enabled_markets).split(",")
            if market.strip().upper() in MARKET_ORDER
        )
        enabled_markets = requested or load_enabled_markets(selection_file_path())
    else:
        enabled_markets = load_enabled_markets(selection_file_path())

    snapshot = collect_seed_universe_snapshot(
        enabled_markets=enabled_markets,
        include_default_universe=_bool_value(args.include_default_universe, True),
    )
    output_path = write_universe_snapshot(args.out, snapshot)
    append_universe_history(args.history_out, snapshot)
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
