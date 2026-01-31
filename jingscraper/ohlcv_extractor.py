"""TradingView OHLCV data extractor with reusable functions."""

import json
import time
import logging
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

from websocket import create_connection, WebSocketTimeoutException, WebSocketConnectionClosedException

from .price import RealTimeData

logger = logging.getLogger(__name__)


class OHLCVExtractor(RealTimeData):
    """Custom OHLCV data extractor with reusable functions."""

    def __init__(self, debug_mode: bool = False):
        # Avoid opening a WebSocket in the base initializer.
        self.request_header = {
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": "en-US,en;q=0.9,fa;q=0.8",
            "Cache-Control": "no-cache",
            "Connection": "Upgrade",
            "Host": "data.tradingview.com",
            "Origin": "https://www.tradingview.com",
            "Pragma": "no-cache",
            "Sec-WebSocket-Extensions": "permessage-deflate; client_max_window_bits",
            "Upgrade": "websocket",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 6.3; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/107.0.0.0 Safari/537.36"
            ),
        }
        self.ws_url = "wss://data.tradingview.com/socket.io/websocket?from=screener%2F"
        self.validate_url = (
            "https://scanner.tradingview.com/symbol?symbol={exchange}%3A{symbol}&fields=market&no_404=false"
        )
        self.ws = None
        self.connect_timeout = 10
        self.connect_retries = 3
        self.connect_backoff = 2
        self.timeout_seconds = 30
        self.debug_mode = debug_mode

        if not debug_mode:
            logging.getLogger("websocket").setLevel(logging.WARNING)
            logger.setLevel(logging.WARNING)

    def _open_websocket(self) -> Optional[str]:
        last_error: Optional[Exception] = None
        for attempt in range(1, self.connect_retries + 1):
            if self.ws is not None:
                try:
                    self.ws.close()
                except Exception:
                    pass
            try:
                self.ws = create_connection(
                    self.ws_url,
                    headers=self.request_header,
                    timeout=self.connect_timeout,
                )
                return None
            except Exception as exc:
                last_error = exc
                if attempt < self.connect_retries:
                    time.sleep(self.connect_backoff * attempt)
        return f"Error initializing WebSocket: {last_error}"

    def get_ohlcv_data(
        self,
        symbol: str,
        timeframe: str = "1D",
        bars_count: int = 10,
        timeout: int = 30,
    ) -> Dict[str, Any]:
        """
        Retrieves OHLCV data for a specific symbol.

        Args:
            symbol: Symbol in 'EXCHANGE:SYMBOL' format (e.g., 'BINANCE:BTCUSDT')
            timeframe: Desired timeframe ('1m', '5m', '15m', '30m', '1h', '1D', '1W', '1M')
            bars_count: Number of historical bars to retrieve
            timeout: Maximum wait time in seconds
        """
        start_time = time.time()
        result = {
            "success": False,
            "symbol": symbol,
            "timeframe": timeframe,
            "bars_requested": bars_count,
            "bars_received": 0,
            "data": [],
            "metadata": {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "processing_time_seconds": 0,
                "error": None,
            },
        }

        try:
            conn_error = self._open_websocket()
            if conn_error:
                result["metadata"]["error"] = conn_error
                return result

            quote_session = self.generate_session(prefix="qs_")
            chart_session = self.generate_session(prefix="cs_")
            self._initialize_sessions(quote_session, chart_session)
            self._add_symbol_to_sessions_custom(
                quote_session, chart_session, symbol, timeframe, bars_count
            )

            data_generator = self.get_data()
            packet_count = 0
            for packet in data_generator:
                packet_count += 1

                if time.time() - start_time > timeout:
                    result["metadata"]["error"] = f"Timeout after {timeout} seconds"
                    break

                if isinstance(packet, dict) and "m" in packet:
                    if packet["m"] == "timescale_update":
                        ohlc_data = self._extract_ohlc_from_packet(packet)
                        if ohlc_data:
                            result["success"] = True
                            result["data"] = ohlc_data
                            result["bars_received"] = len(ohlc_data)
                            break

                    if packet["m"] in ["protocol_error", "critical_error"]:
                        error_msg = packet.get("p", "Unknown error")
                        result["metadata"]["error"] = f"Server error: {error_msg}"
                        break

                if packet_count >= 50:
                    result["metadata"]["error"] = "No OHLC data found in 50 packets"
                    break

        except Exception as error:
            result["metadata"]["error"] = str(error)

        finally:
            result["metadata"]["processing_time_seconds"] = round(time.time() - start_time, 2)
            if self.ws is not None:
                try:
                    self.ws.close()
                except Exception:
                    pass

        return result

    def get_ohlcv_history(
        self,
        symbol: str,
        timeframe: str,
        start_ts: int,
        end_ts: Optional[int] = None,
        chunk_size: int = 5000,
        timeout: int = 60,
        max_packets: int = 500,
        idle_timeout: int = 30,
    ) -> Dict[str, Any]:
        """
        Retrieves OHLCV history between start_ts and end_ts using pagination.

        Args:
            symbol: Symbol in 'EXCHANGE:SYMBOL' format.
            timeframe: Timeframe string (e.g., '5m', '1h', '1D').
            start_ts: Start timestamp (seconds since epoch, UTC).
            end_ts: End timestamp (seconds since epoch, UTC). Defaults to now.
            chunk_size: Bars per request.
            timeout: Maximum total wait time in seconds.
            max_packets: Safety cap to avoid infinite loops.
            idle_timeout: Max seconds to wait without new data after a request.
        """
        start_time = time.time()
        end_ts = end_ts or int(time.time())
        result = {
            "success": False,
            "symbol": symbol,
            "timeframe": timeframe,
            "bars_requested": None,
            "bars_received": 0,
            "data": [],
            "metadata": {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "processing_time_seconds": 0,
                "error": None,
            },
        }

        collected: Dict[int, Dict[str, Any]] = {}

        try:
            conn_error = self._open_websocket()
            if conn_error:
                result["metadata"]["error"] = conn_error
                return result
            try:
                self.ws.settimeout(5)
            except Exception:
                pass

            quote_session = self.generate_session(prefix="qs_")
            chart_session = self.generate_session(prefix="cs_")
            self._initialize_sessions(quote_session, chart_session)
            self._add_symbol_to_sessions_custom(
                quote_session, chart_session, symbol, timeframe, chunk_size
            )

            packet_count = 0
            last_count = 0
            pending_request = False
            last_progress_time = time.time()

            while True:
                if packet_count >= max_packets:
                    result["metadata"]["error"] = "Max packet limit reached"
                    break

                if time.time() - start_time > timeout:
                    result["metadata"]["error"] = f"Timeout after {timeout} seconds"
                    break

                if pending_request and (time.time() - last_progress_time) > idle_timeout:
                    result["metadata"]["error"] = "No additional data returned"
                    break

                try:
                    raw = self.ws.recv()
                except WebSocketTimeoutException:
                    continue
                except WebSocketConnectionClosedException:
                    result["metadata"]["error"] = "WebSocket connection closed"
                    break

                if re.match(r"~m~\d+~m~~h~\d+$", raw):
                    try:
                        self.ws.recv()
                    except WebSocketTimeoutException:
                        pass
                    try:
                        self.ws.send(raw)
                    except Exception:
                        pass
                    continue

                packet_count += 1
                split_result = [x for x in re.split(r"~m~\d+~m~", raw) if x]
                for item in split_result:
                    try:
                        packet = json.loads(item)
                    except Exception:
                        continue

                    if isinstance(packet, dict) and packet.get("m") == "timescale_update":
                        ohlc_data = self._extract_ohlc_from_packet(packet)
                        if not ohlc_data:
                            continue

                        for bar in ohlc_data:
                            timestamp = bar.get("timestamp")
                            if timestamp is None:
                                continue
                            collected[int(timestamp)] = bar

                        if len(collected) > last_count:
                            last_count = len(collected)
                            last_progress_time = time.time()
                            pending_request = False

                        earliest_ts = min(collected.keys())
                        if earliest_ts <= start_ts:
                            result["success"] = True
                            raise StopIteration

                        if not pending_request:
                            self.send_message(
                                "request_more_data",
                                [chart_session, "sds_1", int(chunk_size)],
                            )
                            pending_request = True

                    if isinstance(packet, dict) and packet.get("m") in [
                        "protocol_error",
                        "critical_error",
                    ]:
                        error_msg = packet.get("p", "Unknown error")
                        result["metadata"]["error"] = f"Server error: {error_msg}"
                        raise StopIteration

            if collected and result["metadata"]["error"] is None:
                result["success"] = True

        except StopIteration:
            if result["metadata"]["error"] is None:
                result["success"] = True

        except Exception as error:
            result["metadata"]["error"] = str(error)

        finally:
            result["metadata"]["processing_time_seconds"] = round(time.time() - start_time, 2)
            if self.ws is not None:
                try:
                    self.ws.close()
                except Exception:
                    pass

        if collected:
            filtered = [
                bar
                for ts, bar in sorted(collected.items())
                if start_ts <= ts <= end_ts
            ]
            result["data"] = filtered
            result["bars_received"] = len(filtered)

        if not result["success"] and result["metadata"]["error"] is None:
            result["metadata"]["error"] = "No data returned"

        return result

    def _convert_timeframe(self, timeframe: str) -> str:
        """
        Converts timeframe string to TradingView WebSocket format.
        """
        tf_map = {
            "1m": "1",
            "5m": "5",
            "15m": "15",
            "30m": "30",
            "1h": "60",
            "2h": "120",
            "4h": "240",
            "1D": "1D",
            "1W": "1W",
            "1M": "1M",
        }
        return tf_map.get(timeframe, timeframe)

    def _add_symbol_to_sessions_custom(
        self,
        quote_session: str,
        chart_session: str,
        exchange_symbol: str,
        timeframe: str,
        bars_count: int,
    ):
        """
        Adds the symbol to sessions with custom timeframe and bar count.
        """
        resolve_symbol = json.dumps({"adjustment": "splits", "symbol": exchange_symbol})
        ws_timeframe = self._convert_timeframe(timeframe)

        self.send_message("quote_add_symbols", [quote_session, f"={resolve_symbol}"])
        self.send_message("resolve_symbol", [chart_session, "sds_sym_1", f"={resolve_symbol}"])
        self.send_message(
            "create_series",
            [chart_session, "sds_1", "s1", "sds_sym_1", ws_timeframe, bars_count, ""],
        )
        self.send_message("quote_fast_symbols", [quote_session, exchange_symbol])
        self.send_message(
            "create_study",
            [
                chart_session,
                "st1",
                "st1",
                "sds_1",
                "Volume@tv-basicstudies-246",
                {"length": 20, "col_prev_close": "false"},
            ],
        )
        self.send_message("quote_hibernate_all", [quote_session])

    def _extract_ohlc_from_packet(self, packet: Dict) -> List[Dict[str, Any]]:
        """
        Extracts OHLC data from a response packet.
        """
        ohlc_bars: List[Dict[str, Any]] = []
        ohlc_series = []

        try:
            if "p" in packet and len(packet["p"]) > 1:
                p_data = packet["p"]

                if isinstance(p_data, list):
                    for item in p_data:
                        if isinstance(item, dict) and "sds_1" in item:
                            sds_data = item["sds_1"]

                            if isinstance(sds_data, dict) and "s" in sds_data:
                                ohlc_series = sds_data["s"]

                                for bar in ohlc_series:
                                    if isinstance(bar, dict) and "v" in bar and len(bar["v"]) >= 6:
                                        timestamp = bar["v"][0]
                                        open_price = bar["v"][1]
                                        high_price = bar["v"][2]
                                        low_price = bar["v"][3]
                                        close_price = bar["v"][4]
                                        volume = bar["v"][5]

                                        change_percent = 0
                                        if open_price > 0:
                                            change_percent = (
                                                (close_price - open_price) / open_price
                                            ) * 100

                                        ohlc_bars.append(
                                            {
                                                "timestamp": timestamp,
                                                "datetime": datetime.fromtimestamp(
                                                    timestamp, tz=timezone.utc
                                                ).isoformat(),
                                                "date": datetime.fromtimestamp(
                                                    timestamp, tz=timezone.utc
                                                ).strftime("%Y-%m-%d"),
                                                "time": datetime.fromtimestamp(
                                                    timestamp, tz=timezone.utc
                                                ).strftime("%H:%M:%S"),
                                                "open": open_price,
                                                "high": high_price,
                                                "low": low_price,
                                                "close": close_price,
                                                "volume": volume,
                                                "change_percent": round(change_percent, 4),
                                            }
                                        )

                                break
        except Exception as error:
            logger.debug("Error extracting OHLC data: %s", error)

        return ohlc_bars

    def get_multiple_symbols_ohlcv(
        self,
        symbols: List[str],
        timeframe: str = "1D",
        bars_count: int = 10,
        timeout: int = 30,
    ) -> Dict[str, Any]:
        """
        Retrieves OHLCV data for multiple symbols.
        """
        results = {
            "success": True,
            "total_symbols": len(symbols),
            "successful_symbols": 0,
            "failed_symbols": 0,
            "timeframe": timeframe,
            "bars_requested": bars_count,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": {},
            "errors": {},
        }

        for symbol in symbols:
            if self.debug_mode:
                logger.debug("Processing %s", symbol)

            try:
                extractor = OHLCVExtractor(debug_mode=self.debug_mode)
                symbol_data = extractor.get_ohlcv_data(symbol, timeframe, bars_count, timeout)

                if symbol_data["success"]:
                    results["data"][symbol] = symbol_data
                    results["successful_symbols"] += 1
                else:
                    results["errors"][symbol] = symbol_data["metadata"]["error"]
                    results["failed_symbols"] += 1

            except Exception as error:
                results["errors"][symbol] = str(error)
                results["failed_symbols"] += 1

            time.sleep(1)

        if results["failed_symbols"] > 0:
            results["success"] = False

        return results


def get_ohlcv_json(
    symbol: str,
    timeframe: str = "1D",
    bars_count: int = 10,
    save_to_file: bool = False,
    filename: Optional[str] = None,
    debug: bool = False,
) -> Dict[str, Any]:
    """
    Convenience function to retrieve OHLCV data for a symbol.
    """
    extractor = OHLCVExtractor(debug_mode=debug)
    result = extractor.get_ohlcv_data(symbol, timeframe, bars_count)

    if save_to_file:
        if not filename:
            safe_symbol = symbol.replace(":", "_")
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            filename = f"ohlcv_{safe_symbol}_{timeframe}_{timestamp}.json"

        with open(filename, "w", encoding="utf-8") as file_handle:
            json.dump(result, file_handle, indent=2)

        if debug:
            logger.debug("Data saved to: %s", filename)

    return result


def get_multiple_ohlcv_json(
    symbols: List[str],
    timeframe: str = "1D",
    bars_count: int = 10,
    save_to_file: bool = False,
    filename: Optional[str] = None,
    debug: bool = False,
) -> Dict[str, Any]:
    """
    Convenience function to retrieve OHLCV data for multiple symbols.
    """
    extractor = OHLCVExtractor(debug_mode=debug)
    result = extractor.get_multiple_symbols_ohlcv(symbols, timeframe, bars_count)

    if save_to_file:
        if not filename:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            filename = f"ohlcv_multiple_{timeframe}_{timestamp}.json"

        with open(filename, "w", encoding="utf-8") as file_handle:
            json.dump(result, file_handle, indent=2)

        if debug:
            logger.debug("Data saved to: %s", filename)

    return result
