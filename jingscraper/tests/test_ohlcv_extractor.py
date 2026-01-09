"""
Tests for the OHLCV Extractor module.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from jingscraper.ohlcv_extractor import OHLCVExtractor, get_ohlcv_json


class TestOHLCVExtractor(unittest.TestCase):

    def _skip_if_unavailable(self, result):
        if result["success"]:
            return
        error = (result.get("metadata") or {}).get("error") or ""
        self.skipTest(f"Historical OHLCV unavailable: {error}")

    def test_single_symbol_daily(self):
        """Test fetching daily data for a single symbol."""
        result = get_ohlcv_json(
            symbol="ICEENDEX:ECFZ2026",
            timeframe="1D",
            bars_count=5,
            debug=False,
        )
        self._skip_if_unavailable(result)
        self.assertTrue(result["success"])
        self.assertEqual(result["bars_received"], 5)
        self.assertEqual(result["timeframe"], "1D")
        self.assertTrue(len(result["data"]) > 0)
        print(result)

    def test_intraday_timeframe_conversion(self):
        """Test that intraday timeframes are converted and work correctly."""
        result = get_ohlcv_json(
            symbol="ICEENDEX:ECFZ2026",
            timeframe="1h",
            bars_count=3,
            debug=False,
        )
        self._skip_if_unavailable(result)
        self.assertTrue(result["success"])
        self.assertEqual(result["bars_received"], 3)
        self.assertEqual(result["timeframe"], "1h")
        print(result)

    def test_class_instantiation(self):
        """Test direct class instantiation."""
        extractor = OHLCVExtractor(debug_mode=False)
        self.assertIsInstance(extractor, OHLCVExtractor)
        self.assertIn("wss://data.tradingview.com", extractor.ws_url)


if __name__ == "__main__":
    unittest.main()
