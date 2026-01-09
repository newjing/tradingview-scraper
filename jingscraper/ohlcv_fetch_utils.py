#!/usr/bin/env python3
"""
Shared utilities for OHLCV history fetch scripts.
"""

import json
import math
from datetime import datetime, timezone
from pathlib import Path


TIMEFRAME_MINUTES = {
    "1D": 60 * 24,
    "1h": 60,
    "5m": 5,
}


def parse_date(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def bars_needed(start_dt: datetime, end_dt: datetime, timeframe: str) -> int:
    minutes = TIMEFRAME_MINUTES[timeframe]
    delta_minutes = (end_dt - start_dt).total_seconds() / 60.0
    return max(1, math.ceil(delta_minutes / minutes))


def save_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
