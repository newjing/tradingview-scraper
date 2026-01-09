# Barchart 脚本说明

这些脚本用于从 Barchart 抓取期货分时数据，写入 MySQL，并提供基础的聚合处理。
流程依赖 Selenium Wire 从交互图表页面抓取请求头信息。

## 文件说明
- `app.py`：一键入口。自动获取有效合约代码，抓取数据并写入 MySQL。
- `getExpDate.py`：从合约概览页抓取到期日，找到第一个未过期的合约。
- `getFuturesData.py`：使用 Selenium Wire 获取请求头，然后调用
  `queryminutes.ashx` 接口下载分时数据。
- `mysql.py`：创建 `barchart` 表（不存在则创建）并写入数据。
- `processDataToTimeFrame.py`：从 MySQL 读取 1 分钟数据，进行夏令时修正并聚合到多周期。
- `insertCloseToEuaTable.py`：将最近一天的收盘价写入另一个 MySQL 表（自定义工具）。

## 依赖安装
这些脚本为独立工具，不依赖本仓库的其他模块。运行前先安装依赖：

```bash
pip install selenium selenium-wire requests pandas beautifulsoup4 sqlalchemy pymysql pytz
```

Selenium Wire 需要系统中有 Chrome/Chromium 及匹配版本的 ChromeDriver。

## 基本用法

执行完整流程（有效合约 -> 抓取 -> 写入 MySQL）：

```bash
python scripts/barchart/app.py
```

仅抓取分时数据（返回 pandas DataFrame）：

```bash
python scripts/barchart/getFuturesData.py
```

从指定合约开始查找有效合约：

```bash
python scripts/barchart/getExpDate.py
```

把 1 分钟数据聚合为多周期（15/60/120/600）：

```bash
python scripts/barchart/processDataToTimeFrame.py
```

将昨天收盘价写入目标 `eua.stocks` 表：

```bash
python scripts/barchart/insertCloseToEuaTable.py
```

## 注意事项
- `getFuturesData.py` 使用 `queryminutes.ashx`，当前 `maxrecords` 固定为 1205，
  尚未实现分页，如需更长时间范围需自行添加分页逻辑。
- 数据库账号密码在 `scripts/barchart/mysql.py`、
  `scripts/barchart/processDataToTimeFrame.py`、
  `scripts/barchart/insertCloseToEuaTable.py` 中为硬编码，运行前请修改。
- 表结构以 `scripts/barchart/mysql.py` 中的 `barchart` 表定义为准。
*** End Patch}Oops, apply_patch tool cannot be called with JSON. Should call with raw patch. Let's redo. Use apply_patch correctly. Need ensure ASCII only. OK. Let's run apply_patch.  
