#!/usr/bin/env python3
"""
纯5m测试代码，非生产环境
Standalone 5m OHLCV fetch with pagination.
"""

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from jingscraper.ohlcv_extractor import OHLCVExtractor

from jingscraper.ohlcv_fetch_utils import parse_date, save_json


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch 5m OHLCV history with pagination.")
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
        help="Bars per pagination request.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Max total wait time in seconds.",
    )
    parser.add_argument(
        "--max-packets",
        type=int,
        default=2000,
        help="Safety cap for WebSocket packets.",
    )
    parser.add_argument(
        "--idle-timeout",
        type=int,
        default=60,
        help="Max seconds to wait without new data after a request.",
    )
    args = parser.parse_args()

    start_dt = parse_date(args.start_date)
    start_ts = int(start_dt.timestamp())
    end_ts = int(datetime.now(timezone.utc).timestamp())

    extractor = OHLCVExtractor(debug_mode=False)
    result = extractor.get_ohlcv_history(
        symbol=args.symbol,
        timeframe="5m",
        start_ts=start_ts,
        end_ts=end_ts,
        chunk_size=args.chunk_size,
        timeout=args.timeout,
        max_packets=args.max_packets,
        idle_timeout=args.idle_timeout,
    )

    output_path = Path(args.output_dir) / f"{args.symbol.replace(':', '_')}_5m.json"
    save_json(output_path, result)

    if not result.get("success"):
        error = (result.get("metadata") or {}).get("error")
        print(f"[5m] failed: {error}")
        return 1

    print(f"[5m] saved {result.get('bars_received')} bars -> {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
