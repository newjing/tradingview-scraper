#!/usr/bin/env python3
"""
Single entry point to fetch OHLCV history for a given timeframe.
"""

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from jingscraper.ohlcv_extractor import OHLCVExtractor, get_ohlcv_json

from jingscraper.ohlcv_fetch_utils import bars_needed, parse_date, save_json


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch OHLCV history by timeframe.")
    parser.add_argument(
        "--timeframe",
        required=True,
        choices=["1D", "1h", "5m"],
        help="Timeframe to fetch (1D, 1h, 5m).",
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
        "--output-dir",
        default="data/raw_ohlcv",
        help="Directory to store JSON files.",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=1000,
        help="Bars per pagination request (5m only).",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Max total wait time in seconds (5m only).",
    )
    parser.add_argument(
        "--max-packets",
        type=int,
        default=2000,
        help="Safety cap for WebSocket packets (5m only).",
    )
    parser.add_argument(
        "--idle-timeout",
        type=int,
        default=60,
        help="Max seconds to wait without new data after a request (5m only).",
    )
    args = parser.parse_args()

    start_dt = parse_date(args.start_date)
    end_dt = datetime.now(timezone.utc)
    output_dir = Path(args.output_dir)
    symbol_slug = args.symbol.replace(":", "_")

    if args.timeframe in ("1D", "1h"):
        bars_count = bars_needed(start_dt, end_dt, args.timeframe)
        result = get_ohlcv_json(
            symbol=args.symbol,
            timeframe=args.timeframe,
            bars_count=bars_count,
            save_to_file=False,
            debug=False,
        )
    else:
        extractor = OHLCVExtractor(debug_mode=False)
        result = extractor.get_ohlcv_history(
            symbol=args.symbol,
            timeframe="5m",
            start_ts=int(start_dt.timestamp()),
            end_ts=int(end_dt.timestamp()),
            chunk_size=args.chunk_size,
            timeout=args.timeout,
            max_packets=args.max_packets,
            idle_timeout=args.idle_timeout,
        )

    output_path = output_dir / f"{symbol_slug}_{args.timeframe}.json"
    save_json(output_path, result)

    if not result.get("success"):
        error = (result.get("metadata") or {}).get("error")
        print(f"[{args.timeframe}] failed: {error}")
        return 1

    print(f"[{args.timeframe}] saved {result.get('bars_received')} bars -> {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
