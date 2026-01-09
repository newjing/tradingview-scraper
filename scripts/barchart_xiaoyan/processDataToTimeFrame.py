# -*- coding: utf-8 -*-
"""
从 MySQL 中读取 1 分钟级别的 barchart 数据，按夏令时修正 Timestamp，统一在北京时间 1AM ~ 11AM 范围内，
再对每个交易日进行多周期聚合（15/30/60/120/600 分钟），并输出每个窗口的真实时间戳范围。
"""

import pandas as pd
from sqlalchemy import create_engine

# —— 数据库配置 —— 
db_config = {
    'user':     'barchart',
    'password': 'Ni48dG225dNMW7cR',
    'host':     '8.218.200.99',
    'port':     3306,
    'database': 'barchart'
}
TABLE_NAME = 'barchart'
PERIODS = (15, 60, 120, 600)

def main():
    # 1. 建立数据库连接
    uri = (
        f"mysql+pymysql://{db_config['user']}:{db_config['password']}"
        f"@{db_config['host']}:{db_config['port']}/{db_config['database']}"
    )
    engine = create_engine(uri)

    # 2. 读取原始数据
    sql = (
        "SELECT `Timestamp`, `Open`, `High`, `Low`, `Close`, `Volume` "
        f"FROM `{TABLE_NAME}`"
    )
    df = pd.read_sql(sql, engine)

    # 3. 构造本地时间列（不设为 index）
    df['Datetime'] = (
        pd.to_datetime(df['Timestamp'], unit='s', utc=True)
          .dt.tz_convert('Asia/Shanghai')
          .dt.tz_localize(None)
    )

    # 4. 将日期提取为交易日字段（便于分组）
    df['TradeDate'] = df['Datetime'].dt.date

    # 5. 处理夏令时修正
    adjusted_rows = []
    warn_dates = []

    for day, grp in df.groupby('TradeDate'):
        grp = grp.sort_values('Datetime')
        start_time = grp['Datetime'].iloc[0].time()
        end_time   = grp['Datetime'].iloc[-1].time()

        # 判断是否为夏令时（起始 >= 2:00 且结束 > 10:00）
        if start_time >= pd.to_datetime("02:00").time():
            if end_time > pd.to_datetime("10:00").time():
                # print(f"[夏令时调整] 日期：{day} 起始：{start_time} 结束：{end_time}")
                grp['Timestamp'] = grp['Timestamp'] - 3600  # 时间戳减1小时（单位：秒）
            else:
                print(f"[⚠ 警告] 日期：{day} 起始：{start_time} 结束：{end_time}，起始时间异常但数据不足 10 小时")
                warn_dates.append(str(day))
        adjusted_rows.append(grp)

    # 6. 合并所有调整后的数据
    df_all = pd.concat(adjusted_rows, ignore_index=True)

    # 7. 重建本地时间索引
    df_all['Datetime'] = (
        pd.to_datetime(df_all['Timestamp'], unit='s', utc=True)
          .dt.tz_convert('Asia/Shanghai')
          .dt.tz_localize(None)
          + pd.Timedelta(hours=13)
    )
    df_all.set_index('Datetime', inplace=True)
    df_all.sort_index(inplace=True)

    # 8. 聚合处理
    all_frames = []
    for day, grp in df_all.groupby(df_all.index.normalize()):
        start_ts = grp.index.min()
        end_ts   = start_ts + pd.Timedelta(hours=10)
        daily_trading = grp.loc[start_ts : end_ts].copy()

        for minutes in PERIODS:
            rule = f'{minutes}min'
            daily_agg = (
                daily_trading
                .resample(rule, label='left', closed='left', origin=start_ts)
                .agg(
                    Open   = ('Open',  'first'),
                    High   = ('High',  'max'),
                    Low    = ('Low',   'min'),
                    Close  = ('Close', 'last'),
                    Volume = ('Volume','sum'),
                    # Start  = ('Open',  lambda x: x.index.min()),
                    # End    = ('Open',  lambda x: x.index.max()),
                )
                .dropna(subset=['Open'])
            )
            daily_agg['Date']   = day
            daily_agg['Period'] = f'{minutes}min'
            all_frames.append(daily_agg)

    final = pd.concat(all_frames)

    # 9. 输出 CSV
    for minutes in PERIODS:
        period_label = f'{minutes}min'
        subset = (
            final[final['Period'] == period_label]
            .drop(columns=['Date', 'Period'])
            .copy()
        )
        subset.to_csv(f'{TABLE_NAME}_{period_label}.csv', index_label='PeriodStart')
        print(f"✅ 已写出：{TABLE_NAME}_{period_label}.csv（共 {len(subset)} 条）")

    # 10. 如有警告日期，输出列表
    if warn_dates:
        print("\n⚠ 以下日期数据疑似缺失，请检查源数据：")
        for d in warn_dates:
            print(f"  - {d}")

if __name__ == '__main__':
    main()
