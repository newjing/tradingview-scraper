# TradingView OHLCV (jingscraper)

本仓库仅保留 TradingView OHLCV 的抓取、清洗与合并流程（UTC）。

## EUA 历史数据特别容易手工获取
- Dec25   到  https://www.barchart.com/futures/quotes/CKZ25/interactive-chart
- Dec26   到  https://www.barchart.com/futures/quotes/CKZ26/interactive-chart
- 打开Devtools network中找到  queryminutes.ashx 开头的， 在response里直接复制就好

- 注意展期处理，行业做法是：只用主力合约数据一致到到期，并且【向后复权】：
  - 2025年的全年所有价格 + （2025.12.15那天  Dec26 open - dec25 open）
  - 道理就是像拼接水管，只把到期最后一天的价差统一加上
  - 所以：
    - Dec25的价格，统一加上 （85.95 - 83.67 = 2.28）
    - Dec24的价格，在25的价差  2.28 之上再加上 （66.35 - 64.31 = 2.04）,所以是统一加  4.32

<mark>注意  tradingview抓不到 OI数据，需要到 barchart 上看了手工添加


## 关于时区 & 夏令时 冬令时
    -冬令时：08:00 CET = 07:00 UTC
    -夏令时：08:00 CEST = 06:00 UTC

- 总结：存 UTC，读 Local。这能帮你省去无穷无尽的 if-else 判断。

- A. 数据存储层 (Data Storage)：永远使用 UTC
原则：在 CSV 或数据库中，绝对不要使用当地时间，只存 UTC。

理由：夏令时切换回冬令时的那一天（通常是10月最后一个周日），时间会倒流一小时（例如从 03:00 变回 02:00）。如果你存当地时间，数据库里会出现两个“02:00”，你会分不清哪个是先发生的，导致严重的数据主键冲突。

做法：存 2025-10-27 06:00:00+00:00 (UTC)。

- B. 策略分析层 (Data Analysis)：必须转换为“交易所当地时间”
原则：在把数据加载到 Pandas 或你的回测引擎后，第一件事就是转换时区。
做法：将 UTC 时间转换为 Europe/Berlin (或 Europe/London，取决于具体交易所的主流时区)。
对齐效果：转换后，无论冬天还是夏天，你的 K 线图上，开盘时间永远都是 08:00。这就在逻辑上实现了“时间对齐”。
 08:00–18:00 CET

## 新增功能与用法（本地）
以下为本仓库新增的本地脚本与用法（中文说明）：

- 本地 OHLCV 抓取脚本（UTC）
  - 路径：`jingscraper/fetch.py`、`jingscraper/fetch_5m.py`
  - 示例：
    ```bash
    python3 jingscraper/fetch.py --timeframe 1D --symbol ICEENDEX:ECFZ2026 --start-date 2024-01-02
    python3 jingscraper/fetch.py --timeframe 1h --symbol ICEENDEX:ECFZ2026 --start-date 2024-01-02
    python3 jingscraper/fetch.py --timeframe 5m --symbol ICEENDEX:ECFZ2026 --start-date 2024-01-02
    ```

- 本地清洗脚本（UTC）
  - 路径：`jingscraper/clean.py`、`jingscraper/clean_ohlcv_data.py`
  - 示例：
    ```bash
    python3 jingscraper/clean.py --timeframe 1D --symbol ICEENDEX:ECFZ2026 --start-date 2024-01-02
    python3 jingscraper/clean.py --timeframe 1h --symbol ICEENDEX:ECFZ2026 --start-date 2024-01-02
    python3 jingscraper/clean.py --timeframe 5m --symbol ICEENDEX:ECFZ2026 --start-date 2024-01-02
    ```

- 本地实时补齐与合并（UTC）
  - 路径：`realtime.py`
  - 功能：拉取最近 N 天的 1D/1h/5m 数据，内存清洗后合并到 `data/clean_ohlcv`，不落地临时 JSON/CSV；若 date/time 重复则用新数据覆盖（新数据非空时）。
  - 对齐规则：1D 的 `datetime/time` 取当天 1H 的第一条时间（UTC）。
  - 时间格式：`time` 固定为 `HH:MM:00`，`datetime` 为 `YYYY-MM-DD HH:MM:00`。
  - 示例：
    ```bash
    python3 realtime.py --symbol ICEENDEX:ECFZ2026 --days 5
    ```

- UTC 输出说明
  - `jingscraper/ohlcv_extractor.py` 生成的 `datetime/date/time` 字段均为 UTC。
  - 归档 CSV 默认落在 `data/clean_ohlcv/`（如 `1d_utc.csv`、`1H_utc.csv`、`5m_utc.csv`）。
  - 清洗后 CSV 增加 `datetime` 列（若不存在），并统一 `time` 到 `HH:MM:00`。

- Python 调用示例
  ```python
  from jingscraper import OHLCVExtractor, get_ohlcv_json

  data = get_ohlcv_json("ICEENDEX:ECFZ2026", timeframe="1h", bars_count=5)
  extractor = OHLCVExtractor(debug_mode=False)
  ```

## 依赖
```bash
pip install -r requirements.txt
```

## 目录结构
- `jingscraper/`：抓取、清洗相关脚本
- `realtime.py`：拉取最近 N 天并合并到 CSV
- `data/`：数据目录（保留原样）
