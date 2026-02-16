#!/usr/bin/env python3
"""Rebuild full UTC OHLCV history with contract roll and back-adjustment."""

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from jingscraper.clean_ohlcv_data import _build_open_time_map, _filter_bars
from jingscraper.ohlcv_extractor import OHLCVExtractor
from jingscraper.ohlcv_fetch_utils import parse_date


@dataclass(frozen=True)
class ContractSegment:
    symbol: str
    start_date: str
    end_date: str

    def start_dt(self) -> datetime:
        return parse_date(self.start_date)

    def end_dt(self) -> datetime:
        # End-of-day inclusive in UTC.
        return parse_date(self.end_date) + timedelta(days=1) - timedelta(seconds=1)


@dataclass(frozen=True)
class RollAdjustment:
    cutover_date: str
    delta: Decimal

    def cutover_dt(self) -> datetime:
        return parse_date(self.cutover_date)


SEGMENTS: List[ContractSegment] = [
    ContractSegment("ICEENDEX:ECFZ2024", "2024-01-01", "2024-12-17"),
    ContractSegment("ICEENDEX:ECFZ2025", "2024-12-18", "2025-12-15"),
    ContractSegment("ICEENDEX:ECFZ2026", "2025-12-16", "2026-12-08"),
]

ROLL_ADJUSTMENTS: List[RollAdjustment] = [
    RollAdjustment("2024-12-18", Decimal("2.04")),
    RollAdjustment("2025-12-16", Decimal("2.28")),
]

OUTPUT_FIELDS = {
    "1D": ["datetime", "date", "open", "high", "low", "close", "volume"],
    "1h": ["datetime", "date", "time", "open", "high", "low", "close", "volume"],
    "5m": ["datetime", "date", "time", "open", "high", "low", "close", "volume"],
}

OUTPUT_FILES = {
    "1D": "1d_utc.csv",
    "1h": "1H_utc.csv",
    "5m": "5m_utc.csv",
}


def _parse_iso_datetime_utc(value: str) -> Optional[datetime]:
    text = (value or "").strip()
    if not text:
        return None
    text = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _normalize_time(value: str) -> str:
    text = (value or "").strip()
    parts = text.split(":")
    if len(parts) == 2:
        return f"{parts[0]}:{parts[1]}:00"
    return text


def _row_datetime_utc(row: Dict[str, str]) -> Optional[datetime]:
    lower = {k.lower(): (v or "").strip() for k, v in row.items()}
    if lower.get("datetime"):
        parsed = _parse_iso_datetime_utc(lower["datetime"])
        if parsed:
            return parsed
    if lower.get("date") and lower.get("time"):
        parsed = _parse_iso_datetime_utc(f"{lower['date']} {_normalize_time(lower['time'])}")
        if parsed:
            return parsed
    if lower.get("date"):
        parsed = _parse_iso_datetime_utc(f"{lower['date']} 00:00:00")
        if parsed:
            return parsed
    return None


def _row_date(row: Dict[str, str]) -> str:
    dt = _row_datetime_utc(row)
    return dt.strftime("%Y-%m-%d") if dt else ""


def _row_key(row: Dict[str, str]) -> str:
    dt = _row_datetime_utc(row)
    if dt:
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    return ""


def _row_sort_key(row: Dict[str, str]) -> Tuple[int, Any]:
    key = _row_key(row)
    if not key:
        return (1, "")
    parsed = _parse_iso_datetime_utc(key)
    if parsed:
        return (0, parsed)
    return (0, key)


def _merge_rows(rows: Iterable[Dict[str, str]]) -> List[Dict[str, str]]:
    merged: List[Dict[str, str]] = []
    key_map: Dict[str, int] = {}
    for row in rows:
        key = _row_key(row)
        if not key:
            continue
        if key in key_map:
            idx = key_map[key]
            merged_row = merged[idx].copy()
            for field, value in row.items():
                if (value or "").strip():
                    merged_row[field] = value
            merged[idx] = merged_row
        else:
            merged.append(row)
            key_map[key] = len(merged) - 1
    return sorted(merged, key=_row_sort_key)


def _clean_rows(
    bars: List[Dict[str, Any]],
    start_dt: datetime,
    end_dt: datetime,
    open_time_map: Optional[Dict[str, str]] = None,
) -> List[Dict[str, str]]:
    cleaned = _filter_bars(bars, start_dt, end_dt, open_time_map=open_time_map)
    return [{k: "" if v is None else str(v) for k, v in row.items()} for row in cleaned]


def _fetch_segment(
    symbol: str,
    timeframe: str,
    start_dt: datetime,
    end_dt: datetime,
    chunk_size: int,
    timeout: int,
    max_packets: int,
    idle_timeout: int,
) -> Dict[str, Any]:
    extractor = OHLCVExtractor(debug_mode=False)
    return extractor.get_ohlcv_history(
        symbol=symbol,
        timeframe=timeframe,
        start_ts=int(start_dt.timestamp()),
        end_ts=int(end_dt.timestamp()),
        chunk_size=chunk_size,
        timeout=timeout,
        max_packets=max_packets,
        idle_timeout=idle_timeout,
    )


def _count_by_date(rows: List[Dict[str, str]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for row in rows:
        date = _row_date(row)
        if not date:
            continue
        counts[date] = counts.get(date, 0) + 1
    return counts


def _drop_dates(rows: List[Dict[str, str]], dates: Set[str]) -> List[Dict[str, str]]:
    if not dates:
        return rows
    return [row for row in rows if _row_date(row) not in dates]


def _has_core_price(row: Dict[str, str]) -> bool:
    lower = {k.lower(): (v or "").strip() for k, v in row.items()}
    return bool(lower.get("open") and lower.get("high") and lower.get("low") and lower.get("close"))


def _decimal_to_str(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text if text else "0"


def _apply_back_adjustment(rows: List[Dict[str, str]], adjustments: List[RollAdjustment]) -> None:
    parsed_adjustments = [(adj.cutover_dt(), adj.delta) for adj in adjustments]
    for row in rows:
        date_text = _row_date(row)
        if not date_text:
            continue
        row_dt = parse_date(date_text)
        total = Decimal("0")
        for cutover_dt, delta in parsed_adjustments:
            if row_dt < cutover_dt:
                total += delta
        if total == 0:
            continue
        for field in ("open", "high", "low", "close"):
            raw = (row.get(field) or "").strip()
            if not raw:
                continue
            try:
                row[field] = _decimal_to_str(Decimal(raw) + total)
            except InvalidOperation:
                continue


def _write_csv(path: Path, rows: List[Dict[str, str]], fields: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            out = {field: (row.get(field) or "").strip() for field in fields}
            writer.writerow(out)


def _fetch_and_clean_timeframe(
    timeframe: str,
    segments: List[ContractSegment],
    chunk_size: int,
    timeout: int,
    max_packets: int,
    idle_timeout: int,
    open_time_map: Optional[Dict[str, str]] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, str]]]:
    all_raw_bars: List[Dict[str, Any]] = []
    all_rows: List[Dict[str, str]] = []
    for segment in segments:
        start_dt = segment.start_dt()
        end_dt = segment.end_dt()
        result = _fetch_segment(
            symbol=segment.symbol,
            timeframe=timeframe,
            start_dt=start_dt,
            end_dt=end_dt,
            chunk_size=chunk_size,
            timeout=timeout,
            max_packets=max_packets,
            idle_timeout=idle_timeout,
        )
        if not result.get("success"):
            error = (result.get("metadata") or {}).get("error")
            raise RuntimeError(
                f"[{timeframe}] fetch failed for {segment.symbol} {segment.start_date}~{segment.end_date}: {error}"
            )
        bars = result.get("data") or []
        all_raw_bars.extend(bars)
        all_rows.extend(_clean_rows(bars, start_dt, end_dt, open_time_map=open_time_map))
        print(
            f"[{timeframe}] fetched {len(bars)} bars from {segment.symbol} "
            f"{segment.start_date}~{segment.end_date}"
        )
    return all_raw_bars, _merge_rows(all_rows)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rebuild full historical UTC OHLCV across contract roll segments."
    )
    parser.add_argument(
        "--target-dir",
        default="data/clean_ohlcv_rebuild",
        help="Output directory for rebuilt CSV files.",
    )
    parser.add_argument(
        "--five-min-chunk-size",
        type=int,
        default=1000,
        help="5m fetch chunk size.",
    )
    parser.add_argument(
        "--five-min-timeout",
        type=int,
        default=300,
        help="5m fetch timeout seconds.",
    )
    parser.add_argument(
        "--five-min-max-packets",
        type=int,
        default=2000,
        help="5m fetch max packets.",
    )
    parser.add_argument(
        "--idle-timeout",
        type=int,
        default=60,
        help="Fetch idle timeout seconds.",
    )
    parser.add_argument(
        "--keep-incomplete-closed-days",
        action="store_true",
        help="Keep closed days that do not meet 1/10/120 counts.",
    )
    parser.add_argument(
        "--skip-back-adjustment",
        action="store_true",
        help="Skip back-adjustment on OHLC prices.",
    )
    args = parser.parse_args()

    # Fetch 1h first to build 1D open-time mapping.
    _, rows_1h = _fetch_and_clean_timeframe(
        timeframe="1h",
        segments=SEGMENTS,
        chunk_size=2000,
        timeout=180,
        max_packets=1200,
        idle_timeout=args.idle_timeout,
    )
    one_hour_bars_for_map: List[Dict[str, Any]] = []
    for row in rows_1h:
        dt = _row_datetime_utc(row)
        if dt:
            one_hour_bars_for_map.append({"timestamp": int(dt.timestamp())})
    open_time_map = _build_open_time_map(one_hour_bars_for_map)

    _, rows_1d = _fetch_and_clean_timeframe(
        timeframe="1D",
        segments=SEGMENTS,
        chunk_size=2000,
        timeout=180,
        max_packets=1200,
        idle_timeout=args.idle_timeout,
        open_time_map=open_time_map,
    )
    _, rows_5m = _fetch_and_clean_timeframe(
        timeframe="5m",
        segments=SEGMENTS,
        chunk_size=args.five_min_chunk_size,
        timeout=args.five_min_timeout,
        max_packets=args.five_min_max_packets,
        idle_timeout=args.idle_timeout,
    )

    # Keep only days that exist in 1h for 1D.
    valid_1h_dates = set(_count_by_date(rows_1h).keys())
    rows_1d = [row for row in rows_1d if _row_date(row) in valid_1h_dates]

    # Remove rows with missing core OHLC.
    rows_1d = [row for row in rows_1d if _has_core_price(row)]
    rows_1h = [row for row in rows_1h if _has_core_price(row)]
    rows_5m = [row for row in rows_5m if _has_core_price(row)]

    if not args.keep_incomplete_closed_days:
        c1d = _count_by_date(rows_1d)
        c1h = _count_by_date(rows_1h)
        c5m = _count_by_date(rows_5m)
        all_dates = sorted(set(c1d) | set(c1h) | set(c5m))
        if all_dates:
            last_date = all_dates[-1]
            invalid_closed_dates = {
                d
                for d in all_dates
                if d != last_date
                and (c1d.get(d, 0) != 1 or c1h.get(d, 0) != 10 or c5m.get(d, 0) != 120)
            }
            if invalid_closed_dates:
                rows_1d = _drop_dates(rows_1d, invalid_closed_dates)
                rows_1h = _drop_dates(rows_1h, invalid_closed_dates)
                rows_5m = _drop_dates(rows_5m, invalid_closed_dates)
                print(
                    "[integrity] dropped closed days failing 1/10/120 counts: "
                    f"{len(invalid_closed_dates)}"
                )

    if not args.skip_back_adjustment:
        _apply_back_adjustment(rows_1d, ROLL_ADJUSTMENTS)
        _apply_back_adjustment(rows_1h, ROLL_ADJUSTMENTS)
        _apply_back_adjustment(rows_5m, ROLL_ADJUSTMENTS)
        print("[adjustment] applied back-adjustment events:", len(ROLL_ADJUSTMENTS))

    rows_1d = sorted(_merge_rows(rows_1d), key=_row_sort_key)
    rows_1h = sorted(_merge_rows(rows_1h), key=_row_sort_key)
    rows_5m = sorted(_merge_rows(rows_5m), key=_row_sort_key)

    target_dir = Path(args.target_dir)
    _write_csv(target_dir / OUTPUT_FILES["1D"], rows_1d, OUTPUT_FIELDS["1D"])
    _write_csv(target_dir / OUTPUT_FILES["1h"], rows_1h, OUTPUT_FIELDS["1h"])
    _write_csv(target_dir / OUTPUT_FILES["5m"], rows_5m, OUTPUT_FIELDS["5m"])

    print(f"[done] rebuilt files written to {target_dir}")
    print(f"[done] rows: 1d={len(rows_1d)} 1h={len(rows_1h)} 5m={len(rows_5m)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
