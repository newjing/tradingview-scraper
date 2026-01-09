#!/usr/bin/env python3
"""Fetch and merge recent TradingView OHLCV data into clean CSVs."""

import argparse
import csv
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List


def _run(cmd: List[str]) -> None:
    subprocess.run(cmd, check=True)


def _get_start_date(days: int) -> str:
    now_utc = datetime.now(timezone.utc)
    start_dt = now_utc - timedelta(days=days)
    return start_dt.strftime("%Y-%m-%d")


def _read_csv(path: Path) -> Dict[str, object]:
    if not path.exists():
        return {"fields": [], "rows": []}
    with path.open() as handle:
        reader = csv.DictReader(handle)
        return {"fields": reader.fieldnames or [], "rows": list(reader)}


def _write_csv(path: Path, fields: List[str], rows: List[Dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _merge_rows(
    existing_fields: List[str],
    existing_rows: List[Dict[str, str]],
    new_fields: List[str],
    new_rows: List[Dict[str, str]],
) -> Dict[str, object]:
    if not existing_fields:
        return {"fields": new_fields, "rows": new_rows}

    existing_key_map = {}
    merged_rows = existing_rows[:]

    field_lowers = [f.lower() for f in existing_fields]
    has_time = "time" in field_lowers

    def build_key(row: Dict[str, str]) -> str:
        lower = {k.lower(): (v or "").strip() for k, v in row.items()}
        date = lower.get("date", "")
        time = lower.get("time", "") if has_time else ""
        return f"{date} {time}".strip()

    for idx, row in enumerate(merged_rows):
        key = build_key(row)
        if key:
            existing_key_map[key] = idx

    new_field_map = {f.lower(): f for f in new_fields}

    for new_row in new_rows:
        new_key = build_key(new_row)
        if not new_key:
            continue
        if new_key in existing_key_map:
            idx = existing_key_map[new_key]
            merged = merged_rows[idx].copy()
            for field in existing_fields:
                lower = field.lower()
                src_field = new_field_map.get(lower)
                if not src_field:
                    continue
                value = (new_row.get(src_field) or "").strip()
                if value:
                    merged[field] = value
            merged_rows[idx] = merged
        else:
            appended = {}
            for field in existing_fields:
                lower = field.lower()
                src_field = new_field_map.get(lower)
                appended[field] = (new_row.get(src_field) or "").strip() if src_field else ""
            merged_rows.append(appended)
            existing_key_map[new_key] = len(merged_rows) - 1

    return {"fields": existing_fields, "rows": merged_rows}


def _resolve_target_path(target_dir: Path, timeframe: str, symbol_slug: str) -> Path:
    defaults = {
        "1D": "1d_utc.csv",
        "1h": "1H_utc.csv",
        "5m": "5m_utc.csv",
    }
    candidate = target_dir / defaults[timeframe]
    if candidate.exists():
        return candidate
    return target_dir / f"{symbol_slug}_{timeframe}_utc.csv"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch and merge the latest TradingView OHLCV data."
    )
    parser.add_argument(
        "--symbol",
        default="ICEENDEX:ECFZ2026",
        help="Symbol in EXCHANGE:SYMBOL format.",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=5,
        help="How many days back to fetch (UTC).",
    )
    parser.add_argument(
        "--raw-dir",
        default="data/raw_ohlcv/realtime",
        help="Temp directory for fetched JSON data.",
    )
    parser.add_argument(
        "--clean-dir",
        default="data/clean_ohlcv/realtime",
        help="Temp directory for cleaned CSV data.",
    )
    parser.add_argument(
        "--target-dir",
        default="data/clean_ohlcv",
        help="Directory to merge results into.",
    )
    args = parser.parse_args()

    start_date = _get_start_date(args.days)
    symbol_slug = args.symbol.replace(":", "_")
    raw_dir = Path(args.raw_dir)
    clean_dir = Path(args.clean_dir)
    target_dir = Path(args.target_dir)

    fetch_script = Path(__file__).parent / "jingscraper" / "fetch.py"
    clean_script = Path(__file__).parent / "jingscraper" / "clean.py"

    timeframes = ["1D", "1h", "5m"]
    for timeframe in timeframes:
        _run(
            [
                sys.executable,
                str(fetch_script),
                "--timeframe",
                timeframe,
                "--symbol",
                args.symbol,
                "--start-date",
                start_date,
                "--output-dir",
                str(raw_dir),
            ]
        )
        _run(
            [
                sys.executable,
                str(clean_script),
                "--timeframe",
                timeframe,
                "--symbol",
                args.symbol,
                "--start-date",
                start_date,
                "--input-dir",
                str(raw_dir),
                "--output-dir",
                str(clean_dir),
            ]
        )

        new_csv = clean_dir / f"{symbol_slug}_{timeframe}.csv"
        if not new_csv.exists():
            print(f"[{timeframe}] no cleaned data found at {new_csv}")
            continue

        new_data = _read_csv(new_csv)
        if not new_data["rows"]:
            print(f"[{timeframe}] no new rows to merge")
            continue

        target_csv = _resolve_target_path(target_dir, timeframe, symbol_slug)
        existing = _read_csv(target_csv)
        merged = _merge_rows(
            existing["fields"],
            existing["rows"],
            new_data["fields"],
            new_data["rows"],
        )
        _write_csv(target_csv, merged["fields"], merged["rows"])
        print(f"[{timeframe}] merged {len(new_data['rows'])} rows into {target_csv}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
