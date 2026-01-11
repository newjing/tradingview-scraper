#!/usr/bin/env python3
"""
Clean OHLCV JSON data and output CSV with selected fields.
"""

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Dict, Any, List, Optional


FIELDS = ["datetime", "date", "time", "open", "high", "low", "close", "volume"]


def _parse_date(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def _load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _normalize_row(
    bar: Dict[str, Any],
    open_time_map: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    def normalize_time(value: Optional[str]) -> str:
        if not value:
            return ""
        parts = value.split(":")
        if len(parts) == 2:
            return f"{parts[0]}:{parts[1]}:00"
        if len(parts) == 3:
            return value
        return value

    date_value = bar.get("date")
    time_value = normalize_time(bar.get("time"))
    if date_value and time_value:
        pass
    else:
        timestamp = bar.get("timestamp")
        if timestamp is None:
            return {field: bar.get(field) for field in FIELDS}
        dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        date_value = dt.strftime("%Y-%m-%d")
        time_value = dt.strftime("%H:%M:%S")

    if open_time_map and date_value in open_time_map:
        time_value = normalize_time(open_time_map[date_value])

    if not time_value:
        time_value = "00:00:00"

    return {
        "datetime": f"{date_value} {time_value}",
        "date": date_value,
        "time": time_value,
        "open": bar.get("open"),
        "high": bar.get("high"),
        "low": bar.get("low"),
        "close": bar.get("close"),
        "volume": bar.get("volume"),
    }


def _filter_bars(
    bars: Iterable[Dict[str, Any]],
    start_dt: datetime,
    end_dt: datetime,
    open_time_map: Optional[Dict[str, str]] = None,
) -> List[Dict[str, Any]]:
    cleaned: List[Dict[str, Any]] = []
    for bar in bars:
        timestamp = bar.get("timestamp")
        if timestamp is None:
            continue
        dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        if start_dt <= dt <= end_dt:
            cleaned.append(_normalize_row(bar, open_time_map=open_time_map))
    return cleaned


def _build_open_time_map(bars: Iterable[Dict[str, Any]]) -> Dict[str, str]:
    open_time_map: Dict[str, str] = {}
    open_dt_map: Dict[str, datetime] = {}
    for bar in bars:
        timestamp = bar.get("timestamp")
        if timestamp is None:
            continue
        dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        date_value = dt.strftime("%Y-%m-%d")
        if date_value not in open_dt_map or dt < open_dt_map[date_value]:
            open_dt_map[date_value] = dt
            open_time_map[date_value] = dt.strftime("%H:%M:%S")
    return open_time_map


def _write_csv(path: Path, rows: Iterable[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Clean OHLCV JSON files and output CSV files."
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
        help="Directory that contains JSON files from fetch script.",
    )
    parser.add_argument(
        "--output-dir",
        default="data/clean_ohlcv",
        help="Directory to store CSV output.",
    )
    args = parser.parse_args()

    start_dt = _parse_date(args.start_date)
    end_dt = _parse_date(args.end_date) if args.end_date else datetime.now(timezone.utc)

    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    symbol_slug = args.symbol.replace(":", "_")

    failures = 0
    for timeframe in ("1D", "1h", "5m"):
        json_path = input_dir / f"{symbol_slug}_{timeframe}.json"
        if not json_path.exists():
            print(f"[{timeframe}] missing input: {json_path}")
            failures += 1
            continue

        payload = _load_json(json_path)
        bars = payload.get("data") or []
        cleaned = _filter_bars(bars, start_dt, end_dt)

        csv_path = output_dir / f"{symbol_slug}_{timeframe}.csv"
        _write_csv(csv_path, cleaned)
        print(f"[{timeframe}] wrote {len(cleaned)} rows -> {csv_path}")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
