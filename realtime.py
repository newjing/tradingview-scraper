#!/usr/bin/env python3
"""Fetch and merge recent TradingView OHLCV data into clean CSVs."""

import argparse
import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional, Set, Tuple

from jingscraper.ohlcv_extractor import OHLCVExtractor, get_ohlcv_json
from jingscraper.ohlcv_fetch_utils import bars_needed, parse_date
from jingscraper.clean_ohlcv_data import _build_open_time_map, _filter_bars


def _get_start_date(days: int) -> str:
    now_utc = datetime.now(timezone.utc)
    start_dt = now_utc - timedelta(days=days)
    return start_dt.strftime("%Y-%m-%d")


def _get_start_date_trading_days(trading_days: int) -> str:
    current = datetime.now(timezone.utc).date()
    remaining = trading_days - 1
    while remaining > 0:
        current -= timedelta(days=1)
        if current.weekday() < 5:
            remaining -= 1
    return current.strftime("%Y-%m-%d")


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


def _normalize_time_value(value: str) -> str:
    parts = value.strip().split(":")
    if len(parts) == 2:
        return f"{parts[0]}:{parts[1]}:00"
    return value.strip()


def _parse_iso_datetime_utc(value: str) -> Optional[datetime]:
    text = value.strip()
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


def _row_datetime_utc(row: Dict[str, str]) -> Optional[datetime]:
    lower = {k.lower(): (v or "").strip() for k, v in row.items()}
    datetime_value = lower.get("datetime", "")
    if datetime_value:
        parsed = _parse_iso_datetime_utc(datetime_value)
        if parsed:
            return parsed

    date_value = lower.get("date", "")
    time_value = lower.get("time", "")
    if date_value and time_value:
        parsed = _parse_iso_datetime_utc(f"{date_value} {_normalize_time_value(time_value)}")
        if parsed:
            return parsed
    if date_value:
        parsed = _parse_iso_datetime_utc(f"{date_value} 00:00:00")
        if parsed:
            return parsed
    return None


def _extract_row_date(row: Dict[str, str]) -> str:
    dt = _row_datetime_utc(row)
    if dt:
        return dt.strftime("%Y-%m-%d")
    return ""


def _build_row_key(row: Dict[str, str]) -> str:
    lower = {k.lower(): (v or "").strip() for k, v in row.items()}
    datetime_value = lower.get("datetime", "")
    if datetime_value:
        dt = _parse_iso_datetime_utc(datetime_value)
        if dt:
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        return datetime_value

    date = _extract_row_date(row)
    time = _normalize_time_value(lower.get("time", "")) if lower.get("time", "") else ""
    if date and time:
        return f"{date} {time}"
    return date


def _sort_row_key(row: Dict[str, str]) -> Tuple[int, Any]:
    key = _build_row_key(row)
    if not key:
        return (1, "")
    parsed = _parse_iso_datetime_utc(key)
    if parsed:
        return (0, parsed)
    return (0, key)


def _drop_rows_for_dates(rows: List[Dict[str, str]], dates: Set[str]) -> List[Dict[str, str]]:
    if not dates:
        return rows
    return [row for row in rows if _extract_row_date(row) not in dates]


def _filter_rows_by_dates(rows: List[Dict[str, str]], valid_dates: Set[str]) -> List[Dict[str, str]]:
    if not valid_dates:
        return rows
    return [row for row in rows if _extract_row_date(row) in valid_dates]


def _find_field_name_ci(fields: List[str], candidates: List[str]) -> Optional[str]:
    candidate_set = {name.lower() for name in candidates}
    for field in fields:
        if field.lower() in candidate_set:
            return field
    return None


def _preserve_1d_oi(
    existing_fields: List[str],
    existing_rows: List[Dict[str, str]],
    new_rows: List[Dict[str, str]],
) -> List[Dict[str, str]]:
    oi_aliases = ["oi", "open_interest", "openinterest"]
    existing_oi_field = _find_field_name_ci(existing_fields, oi_aliases)
    if not existing_oi_field or not new_rows:
        return new_rows

    existing_oi_by_date: Dict[str, str] = {}
    for row in existing_rows:
        row_date = _extract_row_date(row)
        if not row_date:
            continue
        oi_value = (row.get(existing_oi_field) or "").strip()
        if oi_value:
            existing_oi_by_date[row_date] = oi_value

    new_oi_field = existing_oi_field
    first_row_fields = list(new_rows[0].keys())
    new_oi_field_in_payload = _find_field_name_ci(first_row_fields, oi_aliases)
    if new_oi_field_in_payload:
        new_oi_field = new_oi_field_in_payload

    preserved_rows: List[Dict[str, str]] = []
    for row in new_rows:
        updated_row = row.copy()
        current_oi = (updated_row.get(new_oi_field) or "").strip()
        if not current_oi:
            row_date = _extract_row_date(updated_row)
            old_oi = existing_oi_by_date.get(row_date, "")
            if old_oi:
                updated_row[new_oi_field] = old_oi
            else:
                updated_row.setdefault(new_oi_field, "")
        preserved_rows.append(updated_row)
    return preserved_rows


def _count_rows_by_date(rows: List[Dict[str, str]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for row in rows:
        date_value = _extract_row_date(row)
        if not date_value:
            continue
        counts[date_value] = counts.get(date_value, 0) + 1
    return counts


def _has_core_price_data(row: Dict[str, str]) -> bool:
    lower = {k.lower(): (v or "").strip() for k, v in row.items()}
    return bool(
        lower.get("open", "")
        and lower.get("high", "")
        and lower.get("low", "")
        and lower.get("close", "")
    )


def _enforce_daily_integrity(
    rows_1d: List[Dict[str, str]],
    rows_1h: List[Dict[str, str]],
    rows_5m: List[Dict[str, str]],
) -> Tuple[List[Dict[str, str]], List[Dict[str, str]], List[Dict[str, str]], Set[str]]:
    rows_1d = [row for row in rows_1d if _has_core_price_data(row)]
    rows_1h = [row for row in rows_1h if _has_core_price_data(row)]
    rows_5m = [row for row in rows_5m if _has_core_price_data(row)]

    counts_1d = _count_rows_by_date(rows_1d)
    counts_1h = _count_rows_by_date(rows_1h)
    counts_5m = _count_rows_by_date(rows_5m)
    all_dates = sorted(set(counts_1d) | set(counts_1h) | set(counts_5m))
    if not all_dates:
        return rows_1d, rows_1h, rows_5m, set()

    last_date = all_dates[-1]
    invalid_closed_dates: Set[str] = set()
    for date_value in all_dates:
        if date_value == last_date:
            continue
        if (
            counts_1d.get(date_value, 0) != 1
            or counts_1h.get(date_value, 0) != 10
            or counts_5m.get(date_value, 0) != 120
        ):
            invalid_closed_dates.add(date_value)

    if not invalid_closed_dates:
        return rows_1d, rows_1h, rows_5m, set()

    rows_1d = _drop_rows_for_dates(rows_1d, invalid_closed_dates)
    rows_1h = _drop_rows_for_dates(rows_1h, invalid_closed_dates)
    rows_5m = _drop_rows_for_dates(rows_5m, invalid_closed_dates)
    return rows_1d, rows_1h, rows_5m, invalid_closed_dates


def _merge_rows(
    existing_fields: List[str],
    existing_rows: List[Dict[str, str]],
    new_fields: List[str],
    new_rows: List[Dict[str, str]],
) -> Dict[str, object]:
    def merge_values(
        base: Dict[str, str],
        incoming: Dict[str, str],
        fields: List[str],
    ) -> Dict[str, str]:
        merged = base.copy()
        for field in fields:
            value = (incoming.get(field) or "").strip()
            if value:
                merged[field] = value
        return merged

    if not existing_fields:
        if not new_rows:
            return {"fields": new_fields, "rows": []}
        new_rows_deduped: List[Dict[str, str]] = []
        new_key_map: Dict[str, int] = {}
        for row in new_rows:
            key = _build_row_key(row)
            if not key:
                continue
            if key in new_key_map:
                idx = new_key_map[key]
                new_rows_deduped[idx] = merge_values(
                    new_rows_deduped[idx],
                    row,
                    new_fields,
                )
            else:
                new_rows_deduped.append(row)
                new_key_map[key] = len(new_rows_deduped) - 1
        return {"fields": new_fields, "rows": sorted(new_rows_deduped, key=_sort_row_key)}

    existing_key_map: Dict[str, int] = {}
    merged_rows: List[Dict[str, str]] = []
    for row in existing_rows:
        key = _build_row_key(row)
        if not key:
            continue
        if key in existing_key_map:
            idx = existing_key_map[key]
            merged_rows[idx] = merge_values(merged_rows[idx], row, existing_fields)
        else:
            merged_rows.append(row)
            existing_key_map[key] = len(merged_rows) - 1

    new_field_map = {f.lower(): f for f in new_fields}
    new_rows_deduped: List[Dict[str, str]] = []
    new_key_map: Dict[str, int] = {}
    for row in new_rows:
        key = _build_row_key(row)
        if not key:
            continue
        if key in new_key_map:
            idx = new_key_map[key]
            new_rows_deduped[idx] = merge_values(
                new_rows_deduped[idx],
                row,
                new_fields,
            )
        else:
            new_rows_deduped.append(row)
            new_key_map[key] = len(new_rows_deduped) - 1

    for new_row in new_rows_deduped:
        new_key = _build_row_key(new_row)
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

    return {"fields": existing_fields, "rows": sorted(merged_rows, key=_sort_row_key)}


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
        chunk_size=1000,
        timeout=300,
        max_packets=2000,
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
        "--trading-days",
        type=int,
        default=0,
        help="How many trading days back to fetch (UTC, weekdays only).",
    )
    parser.add_argument(
        "--target-dir",
        default="data/clean_ohlcv",
        help="Directory to merge results into.",
    )
    args = parser.parse_args()

    if args.trading_days and args.trading_days > 0:
        start_date = _get_start_date_trading_days(args.trading_days)
    else:
        start_date = _get_start_date(args.days)
    start_dt = parse_date(start_date)
    end_dt = datetime.now(timezone.utc)
    symbol_slug = args.symbol.replace(":", "_")
    target_dir = Path(args.target_dir)

    timeframes = ["1h", "1D", "5m"]
    open_time_map = None
    merged_payloads: Dict[str, Dict[str, object]] = {}
    valid_1h_dates: Set[str] = set()
    for timeframe in timeframes:
        target_csv = _resolve_target_path(target_dir, timeframe, symbol_slug)
        existing = _read_csv(target_csv)
        result = _fetch_bars(args.symbol, timeframe, start_dt, end_dt)
        new_rows: List[Dict[str, str]] = []
        if not result.get("success"):
            error = (result.get("metadata") or {}).get("error")
            print(f"[{timeframe}] fetch failed: {error}")
        else:
            bars = result.get("data") or []
            if timeframe == "1h":
                open_time_map = _build_open_time_map(bars)
            if timeframe == "1D":
                new_rows = _clean_rows(bars, start_dt, end_dt, open_time_map=open_time_map)
            else:
                new_rows = _clean_rows(bars, start_dt, end_dt)

        if timeframe == "1D" and valid_1h_dates:
            new_rows = _filter_rows_by_dates(new_rows, valid_1h_dates)
        if timeframe == "1D":
            new_rows = _preserve_1d_oi(
                existing["fields"],
                existing["rows"],
                new_rows,
            )

        dates_to_replace = {d for d in (_extract_row_date(row) for row in new_rows) if d}
        existing_rows = _drop_rows_for_dates(existing["rows"], dates_to_replace)

        if not new_rows:
            if not existing["rows"]:
                print(f"[{timeframe}] no new rows to merge")
            else:
                merged = _merge_rows(
                    existing["fields"],
                    existing_rows,
                    existing["fields"],
                    [],
                )
                rows_to_write = merged["rows"]
                if timeframe == "1h":
                    valid_1h_dates = {d for d in (_extract_row_date(row) for row in rows_to_write) if d}
                if timeframe == "1D" and valid_1h_dates:
                    rows_to_write = _filter_rows_by_dates(rows_to_write, valid_1h_dates)
                merged_payloads[timeframe] = {
                    "fields": merged["fields"],
                    "rows": rows_to_write,
                    "path": target_csv,
                }
                removed = len(existing["rows"]) - len(rows_to_write)
                if removed > 0:
                    print(f"[{timeframe}] deduped {removed} rows in {target_csv}")
                else:
                    print(f"[{timeframe}] no new rows to merge")
            continue

        new_fields = list(new_rows[0].keys())
        merged = _merge_rows(
            existing["fields"],
            existing_rows,
            new_fields,
            new_rows,
        )
        rows_to_write = merged["rows"]
        if timeframe == "1h":
            valid_1h_dates = {d for d in (_extract_row_date(row) for row in rows_to_write) if d}
        if timeframe == "1D" and valid_1h_dates:
            rows_to_write = _filter_rows_by_dates(rows_to_write, valid_1h_dates)

        merged_payloads[timeframe] = {
            "fields": merged["fields"],
            "rows": rows_to_write,
            "path": target_csv,
        }
        print(
            f"[{timeframe}] merged {len(new_rows)} rows into {target_csv} "
            f"(replace_days={len(dates_to_replace)})"
        )

    if {"1D", "1h", "5m"}.issubset(set(merged_payloads)):
        clean_1d, clean_1h, clean_5m, invalid_closed_dates = _enforce_daily_integrity(
            merged_payloads["1D"]["rows"],  # type: ignore[index]
            merged_payloads["1h"]["rows"],  # type: ignore[index]
            merged_payloads["5m"]["rows"],  # type: ignore[index]
        )
        merged_payloads["1D"]["rows"] = sorted(clean_1d, key=_sort_row_key)
        merged_payloads["1h"]["rows"] = sorted(clean_1h, key=_sort_row_key)
        merged_payloads["5m"]["rows"] = sorted(clean_5m, key=_sort_row_key)
        if invalid_closed_dates:
            print(
                "[integrity] dropped closed trading days with bad counts: "
                f"{len(invalid_closed_dates)}"
            )

    for timeframe in timeframes:
        payload = merged_payloads.get(timeframe)
        if not payload:
            continue
        _write_csv(
            payload["path"],  # type: ignore[arg-type]
            payload["fields"],  # type: ignore[arg-type]
            payload["rows"],  # type: ignore[arg-type]
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
