#!/usr/bin/env python3
"""
Single entry point to clean OHLCV JSON data for a given timeframe.
"""

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from jingscraper.clean_ohlcv_data import _filter_bars, _load_json, _parse_date, _write_csv


def main() -> int:
    parser = argparse.ArgumentParser(description="Clean OHLCV JSON by timeframe.")
    parser.add_argument(
        "--timeframe",
        required=True,
        choices=["1D", "1h", "5m"],
        help="Timeframe to clean (1D, 1h, 5m).",
    )
    parser.add_argument(
        "--symbol",
        default="ICEENDEX:ECFZ2026",
        help="Symbol in EXCHANGE:SYMBOL format.",
    )
    parser.add_argument(
        "--start-date",
        default="2024-01-02",
        help="Start date in YYYY-MM-DD (UTC).",
    )
    parser.add_argument(
        "--end-date",
        default=None,
        help="End date in YYYY-MM-DD (UTC). Defaults to now.",
    )
    parser.add_argument(
        "--input-dir",
        default="data/raw_ohlcv",
        help="Directory that contains JSON files from fetch.",
    )
    parser.add_argument(
        "--output-dir",
        default="data/clean_ohlcv",
        help="Directory to store CSV output.",
    )
    args = parser.parse_args()

    start_dt = _parse_date(args.start_date)
    end_dt = _parse_date(args.end_date) if args.end_date else datetime.now(timezone.utc)

    symbol_slug = args.symbol.replace(":", "_")
    json_path = Path(args.input_dir) / f"{symbol_slug}_{args.timeframe}.json"
    if not json_path.exists():
        print(f"[{args.timeframe}] missing input: {json_path}")
        return 1

    payload = _load_json(json_path)
    bars = payload.get("data") or []
    cleaned = _filter_bars(bars, start_dt, end_dt)

    csv_path = Path(args.output_dir) / f"{symbol_slug}_{args.timeframe}.csv"
    _write_csv(csv_path, cleaned)
    print(f"[{args.timeframe}] wrote {len(cleaned)} rows -> {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
