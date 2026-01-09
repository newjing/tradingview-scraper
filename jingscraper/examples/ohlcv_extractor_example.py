"""
Example usage of the OHLCV Extractor module.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from jingscraper.ohlcv_extractor import (
    OHLCVExtractor,
    get_multiple_ohlcv_json,
    get_ohlcv_json,
)


def example_single_symbol():
    """Example 1: Fetch OHLCV data for a single symbol using convenience function."""
    print("=" * 60)
    print("Example 1: Single Symbol - BTCUSDT (1D, 10 bars)")
    print("=" * 60)

    result = get_ohlcv_json(
        symbol="BINANCE:BTCUSDT",
        timeframe="1D",
        bars_count=10,
        save_to_file=True,
        debug=True,
    )

    if result["success"]:
        print(f"Success. Retrieved {result['bars_received']} bars")
        print(
            f"Latest bar: {result['data'][-1]['date']} - Close: {result['data'][-1]['close']}"
        )
    else:
        print(f"Error: {result['metadata']['error']}")

    return result


def example_multiple_symbols():
    """Example 2: Fetch OHLCV data for multiple symbols."""
    print("\n" + "=" * 60)
    print("Example 2: Multiple Symbols - Crypto Portfolio")
    print("=" * 60)

    symbols = ["BINANCE:BTCUSDT", "BINANCE:ETHUSDT", "BINANCE:ADAUSDT"]

    result = get_multiple_ohlcv_json(
        symbols=symbols,
        timeframe="1h",
        bars_count=5,
        save_to_file=True,
        debug=False,
    )

    print(f"Processed {result['total_symbols']} symbols")
    print(f"Successful: {result['successful_symbols']}")
    print(f"Failed: {result['failed_symbols']}")

    if result["errors"]:
        print("Errors:")
        for symbol, error in result["errors"].items():
            print(f"  - {symbol}: {error}")

    return result


def example_class_usage():
    """Example 3: Using the OHLCVExtractor class directly."""
    print("\n" + "=" * 60)
    print("Example 3: Direct Class Usage - Custom Configuration")
    print("=" * 60)

    extractor = OHLCVExtractor(debug_mode=True)

    result = extractor.get_ohlcv_data(
        symbol="BINANCE:ETHUSDT",
        timeframe="15m",
        bars_count=20,
        timeout=45,
    )

    if result["success"]:
        print(
            f"Retrieved {result['bars_received']} bars in "
            f"{result['metadata']['processing_time_seconds']}s"
        )

        closes = [bar["close"] for bar in result["data"]]
        avg_close = sum(closes) / len(closes)
        max_close = max(closes)
        min_close = min(closes)

        print("Statistics:")
        print(f"  Average Close: {avg_close}")
        print(f"  Max Close: {max_close}")
        print(f"  Min Close: {min_close}")
    else:
        print(f"Error: {result['metadata']['error']}")

    return result


def example_different_timeframes():
    """Example 4: Comparing different timeframes."""
    print("\n" + "=" * 60)
    print("Example 4: Different Timeframes - Same Symbol")
    print("=" * 60)

    symbol = "BINANCE:BTCUSDT"
    timeframes = ["1h", "4h", "1D"]

    for tf in timeframes:
        result = get_ohlcv_json(
            symbol=symbol,
            timeframe=tf,
            bars_count=3,
            debug=False,
        )

        if result["success"]:
            latest = result["data"][-1]
            print(f"{tf:>3} - Close: {latest['close']} | Change: {latest['change_percent']:.2f}%")
        else:
            print(f"{tf:>3} - Error: {result['metadata']['error']}")


if __name__ == "__main__":
    print("\nOHLCV Extractor - Usage Examples")
    print("=" * 60)

    example_single_symbol()
    example_multiple_symbols()
    example_class_usage()
    example_different_timeframes()

    print("=" * 60)
    print("All examples completed.")
    print("=" * 60)
