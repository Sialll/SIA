from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from sia import notifier_pipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill dashboard_snapshots.signal_source from price_ticks.")
    parser.add_argument("--db-path", required=True, help="Path to trading_signal_notifier sqlite db")
    parser.add_argument(
        "--rewrite",
        action="store_true",
        help="Rewrite existing signal_source values instead of filling only empty rows",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    db_path = Path(args.db_path).expanduser()
    notifier_pipeline.init_db(str(db_path))

    with sqlite3.connect(str(db_path)) as conn:
        rows = conn.execute(
            """
            SELECT id, ticker, ts, price, signal_source
            FROM dashboard_snapshots
            ORDER BY id ASC
            """
        ).fetchall()

        scanned = 0
        updated = 0
        unchanged = 0
        unresolved = 0
        by_source: dict[str, int] = {}

        for row_id, ticker, ts, price, current_source in rows:
            scanned += 1
            existing = None if current_source in (None, "") else str(current_source)
            if existing is not None and not args.rewrite:
                unchanged += 1
                by_source[existing] = by_source.get(existing, 0) + 1
                continue

            inferred = notifier_pipeline.infer_signal_source(
                conn,
                ticker=str(ticker),
                snapshot_ts=int(ts),
                snapshot_price=float(price),
            )
            if inferred is None:
                unresolved += 1
                continue

            if inferred == existing:
                unchanged += 1
            else:
                conn.execute(
                    "UPDATE dashboard_snapshots SET signal_source = ? WHERE id = ?",
                    (inferred, int(row_id)),
                )
                updated += 1
            by_source[inferred] = by_source.get(inferred, 0) + 1

        conn.commit()

    print(f"scanned={scanned}")
    print(f"updated={updated}")
    print(f"unchanged={unchanged}")
    print(f"unresolved={unresolved}")
    if by_source:
        print("sources=" + ",".join(f"{source}:{count}" for source, count in sorted(by_source.items())))
    else:
        print("sources=")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
