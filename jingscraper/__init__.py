"""Local TradingView helpers."""

from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .ohlcv_extractor import (  # noqa: F401
        OHLCVExtractor,
        get_ohlcv_json,
        get_multiple_ohlcv_json,
    )

__all__ = [
    "OHLCVExtractor",
    "get_ohlcv_json",
    "get_multiple_ohlcv_json",
]


def __getattr__(name: str):
    if name in {"OHLCVExtractor", "get_ohlcv_json", "get_multiple_ohlcv_json"}:
        module = import_module("jingscraper.ohlcv_extractor")
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
