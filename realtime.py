#!/usr/bin/env python3
"""Fetch and merge recent TradingView OHLCV data into clean CSVs."""

import argparse
import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional

from jingscraper.ohlcv_extractor import OHLCVExtractor, get_ohlcv_json
from jingscraper.ohlcv_fetch_utils import bars_needed, parse_date
from jingscraper.clean_ohlcv_data import _build_open_time_map, _filter_bars


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


def _fetch_bars(
    symbol: str,
    timeframe: str,
    start_dt: datetime,
    end_dt: datetime,
) -> Dict[str, Any]:
    if timeframe in ("1D", "1h"):
        bars_count = bars_needed(start_dt, end_dt, timeframe)
        return get_ohlcv_json(
            symbol=symbol,
            timeframe=timeframe,
            bars_count=bars_count,
            save_to_file=False,
            debug=False,
        )
    extractor = OHLCVExtractor(debug_mode=False)
    return extractor.get_ohlcv_history(
        symbol=symbol,
        timeframe="5m",
        start_ts=int(start_dt.timestamp()),
        end_ts=int(end_dt.timestamp()),
        chunk_size=5000,
        timeout=120,
        max_packets=800,
        idle_timeout=60,
    )


def _clean_rows(
    bars: List[Dict[str, Any]],
    start_dt: datetime,
    end_dt: datetime,
    open_time_map: Optional[Dict[str, str]] = None,
) -> List[Dict[str, str]]:
    cleaned = _filter_bars(bars, start_dt, end_dt, open_time_map=open_time_map)
    normalized: List[Dict[str, str]] = []
    for row in cleaned:
        normalized.append({key: "" if value is None else str(value) for key, value in row.items()})
    return normalized


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
        "--target-dir",
        default="data/clean_ohlcv",
        help="Directory to merge results into.",
    )
    args = parser.parse_args()

    start_date = _get_start_date(args.days)
    start_dt = parse_date(start_date)
    end_dt = datetime.now(timezone.utc)
    symbol_slug = args.symbol.replace(":", "_")
    target_dir = Path(args.target_dir)

    timeframes = ["1h", "1D", "5m"]
    open_time_map = None
    for timeframe in timeframes:
        result = _fetch_bars(args.symbol, timeframe, start_dt, end_dt)
        if not result.get("success"):
            error = (result.get("metadata") or {}).get("error")
            print(f"[{timeframe}] fetch failed: {error}")
            continue

        bars = result.get("data") or []
        if timeframe == "1h":
            open_time_map = _build_open_time_map(bars)
        if timeframe == "1D":
            new_rows = _clean_rows(bars, start_dt, end_dt, open_time_map=open_time_map)
        else:
            new_rows = _clean_rows(bars, start_dt, end_dt)
        if not new_rows:
            print(f"[{timeframe}] no new rows to merge")
            continue

        new_fields = list(new_rows[0].keys())
        target_csv = _resolve_target_path(target_dir, timeframe, symbol_slug)
        existing = _read_csv(target_csv)
        merged = _merge_rows(
            existing["fields"],
            existing["rows"],
            new_fields,
            new_rows,
        )
        _write_csv(target_csv, merged["fields"], merged["rows"])
        print(f"[{timeframe}] merged {len(new_rows)} rows into {target_csv}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
