from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any


DEFAULT_PRICE_HORIZONS = "1,3,5,10,30m,1h,day_close,next_open"
DEFAULT_POSITION_HORIZONS = "3,30m,1h,day_close,next_open"


@dataclass(frozen=True)
class BacktestHorizon:
    key: str
    label: str
    kind: str
    value: int | None = None


def parse_horizon_specs(raw: str) -> list[BacktestHorizon]:
    specs: list[BacktestHorizon] = []
    seen: set[str] = set()
    for token in [item.strip().lower() for item in raw.split(",") if item.strip()]:
        spec = _parse_single_horizon(token)
        if spec.key in seen:
            continue
        seen.add(spec.key)
        specs.append(spec)
    return specs


def _parse_single_horizon(token: str) -> BacktestHorizon:
    if token.isdigit():
        ticks = max(1, int(token))
        return BacktestHorizon(key=f"tick:{ticks}", label=f"+{ticks} tick", kind="tick", value=ticks)
    if token.endswith("m") and token[:-1].isdigit():
        minutes = max(1, int(token[:-1]))
        return BacktestHorizon(key=f"minutes:{minutes}", label=f"{minutes}분", kind="minutes", value=minutes)
    if token.endswith("h") and token[:-1].isdigit():
        hours = max(1, int(token[:-1]))
        minutes = hours * 60
        return BacktestHorizon(key=f"minutes:{minutes}", label=f"{hours}시간", kind="minutes", value=minutes)
    if token == "day_close":
        return BacktestHorizon(key="day_close", label="당일 종가", kind="day_close")
    if token == "next_open":
        return BacktestHorizon(key="next_open", label="익일 시가", kind="next_open")
    raise ValueError(f"Unsupported horizon token: {token}")


def resolve_exit_index(series: list[Any], entry_index: int, entry_ts: int, horizon: BacktestHorizon) -> int | None:
    start_index = entry_index + 1
    if start_index >= len(series):
        return None
    if horizon.kind == "tick":
        exit_index = start_index + int(horizon.value or 1) - 1
        return exit_index if exit_index < len(series) else None

    entry_dt = dt.datetime.fromtimestamp(entry_ts)
    if horizon.kind == "minutes":
        target_ts = entry_ts + int(horizon.value or 0) * 60
        for index in range(start_index, len(series)):
            if int(series[index].ts) >= target_ts:
                return index
        return None

    if horizon.kind == "day_close":
        exit_index: int | None = None
        for index in range(start_index, len(series)):
            point_dt = dt.datetime.fromtimestamp(int(series[index].ts))
            if point_dt.date() != entry_dt.date():
                break
            exit_index = index
        return exit_index

    if horizon.kind == "next_open":
        for index in range(start_index, len(series)):
            point_dt = dt.datetime.fromtimestamp(int(series[index].ts))
            if point_dt.date() > entry_dt.date():
                return index
        return None

    return None
