---
name: tradingview-jingscraper
description: Workflows for local TradingView OHLCV fetching/cleaning/merging with UTC handling via jingscraper scripts.
metadata:
  short-description: Local TradingView OHLCV workflows
---

# tradingview-jingscraper

Use this skill when the user wants to fetch/clean/merge TradingView OHLCV data in this repo, or asks about the local jingscraper scripts and UTC outputs.

## Scope
- Local scripts live under `jingscraper/`, plus root scripts `realtime.py` and `rebuild_history.py`.
- Outputs are written to `data/raw_ohlcv/` and `data/clean_ohlcv/`.
- All OHLCV timestamps should be treated as UTC.

## Key files
- `jingscraper/ohlcv_extractor.py`: TradingView OHLCV fetcher. Uses UTC for datetime/date/time fields.
- `jingscraper/fetch.py`: fetch JSON for `1D`, `1h`, `5m`.
- `jingscraper/clean.py` and `jingscraper/clean_ohlcv_data.py`: clean JSON to CSV.
- `realtime.py`: fetch recent N days, clean in-memory, then merge into `data/clean_ohlcv` with de-dupe by date/time and overwrite if new values are non-empty. No temp JSON/CSV files are written.
- `rebuild_history.py`: full rebuild from contract segments in UTC, with optional strict daily integrity checks and back-adjustment.

## Workflow
1) Fetch recent data
- Use `jingscraper/fetch.py` for each timeframe.
- Pass `--start-date` in UTC (YYYY-MM-DD).

2) Clean to CSV
- Use `jingscraper/clean.py` for each timeframe with matching `--start-date`.

3) Merge to target CSVs
- Use `realtime.py` to automate steps 1-2 and merge into `data/clean_ohlcv`.
- When date/time duplicates exist, new non-empty values overwrite existing ones.

4) Full-history rebuild (no impact on realtime flow)
- Use `rebuild_history.py` when rebuilding history from scratch.
- Default contract segments (UTC):
  - `2024-01-01 ~ 2024-12-17` -> `ICEENDEX:ECFZ2024`
  - `2024-12-18 ~ 2025-12-15` -> `ICEENDEX:ECFZ2025`
  - `2025-12-16 ~ 2026-12-08` -> `ICEENDEX:ECFZ2026`
- Default back-adjustment:
  - before `2024-12-18`: `+2.04` on OHLC
  - before `2025-12-16`: additional `+2.28` on OHLC
  - earliest segment total: `+4.32`

## Commands
- Fetch only:
  - `python3 jingscraper/fetch.py --timeframe 1D --symbol ICEENDEX:ECFZ2026 --start-date 2024-01-02`
  - `python3 jingscraper/fetch.py --timeframe 1h --symbol ICEENDEX:ECFZ2026 --start-date 2024-01-02`
  - `python3 jingscraper/fetch.py --timeframe 5m --symbol ICEENDEX:ECFZ2026 --start-date 2024-01-02`

- Clean only:
  - `python3 jingscraper/clean.py --timeframe 1D --symbol ICEENDEX:ECFZ2026 --start-date 2024-01-02`
  - `python3 jingscraper/clean.py --timeframe 1h --symbol ICEENDEX:ECFZ2026 --start-date 2024-01-02`
  - `python3 jingscraper/clean.py --timeframe 5m --symbol ICEENDEX:ECFZ2026 --start-date 2024-01-02`

- Realtime merge:
  - `python3 realtime.py --symbol ICEENDEX:ECFZ2026 --days 5`

- Full rebuild:
  - `python3 rebuild_history.py`
  - `python3 rebuild_history.py --target-dir data/clean_ohlcv_rebuild --five-min-timeout 300 --five-min-max-packets 2000`

## Notes
- UTC output is required; if timestamps appear in local time, check `jingscraper/ohlcv_extractor.py` for `datetime.now(timezone.utc)` and `datetime.fromtimestamp(..., tz=timezone.utc)` usage.
- Default target CSVs: `data/clean_ohlcv/1d_utc.csv`, `data/clean_ohlcv/1H_utc.csv`, `data/clean_ohlcv/5m_utc.csv`.
- 清洗输出包含 `datetime` 列（若不存在则补齐），`time` 统一为 `HH:MM:00`。
- 1D 的 `datetime/time` 取当天 1H 第一条数据时间（UTC）以便对齐。

## 数据合并规则细节
- 合并键：按 `date` 或 `date+time` 去重。
  - 若 CSV 有 `time` 列，用 `date+time` 作为唯一键。
  - 若没有 `time` 列（如 1D），仅用 `date`。
- 覆盖规则：当新数据同键的字段值**非空**时覆盖旧值；新数据为空则保留旧值。
- 目标文件若不存在：自动创建，字段以新数据为准。
- 目标文件存在但字段更全：保留目标文件字段顺序，尽量填充新数据中同名字段。

## rebuild_history 规则
- 默认输出到 `data/clean_ohlcv_rebuild/`，不覆盖 realtime 常用目标目录。
- 先抓取并清洗 1h，再用 1h 的开盘时间映射对齐 1D 的 `datetime`。
- 默认开启完整性约束：除最后交易日外，强制 `1d=1`、`1h=10`、`5m=120`，不满足则整日剔除。
- 可用 `--keep-incomplete-closed-days` 关闭整日剔除。
- 可用 `--skip-back-adjustment` 只重建不复权。

## 排错指南
- 循环导入报错：确保 `jingscraper/__init__.py` 使用懒加载；不要在 `tradingview_scraper/symbols/stream/__init__.py` 里直接 import `jingscraper.ohlcv_extractor`。
- 没有写入新行：检查 `realtime.py` 生成的 `data/clean_ohlcv/realtime/*.csv` 是否为空；若为空，多为请求失败或符号/日期不匹配。
- 时间非 UTC：检查 `jingscraper/ohlcv_extractor.py` 是否用 `datetime.now(timezone.utc)` 和 `datetime.fromtimestamp(..., tz=timezone.utc)`。
- 1h/5m 数据不全：增大 `fetch.py` 的 `--chunk-size`/`--timeout`/`--max-packets` 参数。
