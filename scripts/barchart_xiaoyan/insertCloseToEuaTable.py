# 脚本说明：本脚本用于将期货数据插入 eua.timing-carbon.com 数据库的 stocks 表中
from sqlalchemy import create_engine, text
import datetime
import pytz

# ==== 源数据库配置 ====
DB_CONFIG = {
    'user': 'barchart',
    'password': 'Ni48dG225dNMW7cR',
    'host': 'localhost',
    'port': 3306,
    'database': 'barchart'
}
TABLE_NAME = 'barchart'
DATE_FIELD = 'date'
SORT_FIELD = 'time'
# 获取昨天的日期
yesterday = (datetime.date.today() - datetime.timedelta(days=1)).strftime('%Y-%m-%d')
DATE_VALUE = yesterday

# ==== 目标数据库配置 ====
TARGET_DB_CONFIG = {
    'user': 'eua',
    'password': 'N4LtEPbK2dHpKpSd',
    'host': '127.0.0.1',
    'port': 3306,
    'database': 'eua'
}
TARGET_TABLE = 'stocks'
TARGET_CLOSE_FIELD = 'close'
TARGET_TS_FIELD = 'date'  # 目标表存东八区0点时间戳

def make_conn_str(conf):
    return f"mysql+pymysql://{conf['user']}:{conf['password']}@{conf['host']}:{conf['port']}/{conf['database']}"

def fetch_last_row(engine, table, date_field, date_value, sort_field):
    sql = text(f"""
        SELECT * FROM {table}
        WHERE {date_field} = :date_value
        ORDER BY {sort_field} DESC
        LIMIT 1
    """)
    with engine.connect() as conn:
        row = conn.execute(sql, {"date_value": date_value}).fetchone()
        if not row:
            print(f"未找到 {date_field} = {date_value} 的数据")
            return None
        return dict(row._mapping) if hasattr(row, "_mapping") else dict(row)

def to_china_0am_timestamp(utc_ts):
    dt_utc = datetime.datetime.fromtimestamp(utc_ts, tz=datetime.timezone.utc)
    china_tz = pytz.timezone('Asia/Shanghai')
    dt_china = dt_utc.astimezone(china_tz)
    dt_china_0am = dt_china.replace(hour=0, minute=0, second=0, microsecond=0)
    return int(dt_china_0am.timestamp())

def get_now_str():
    return datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

def insert_or_update(engine, table, close_field, ts_field, close, ts):
    now_str = get_now_str()
    # 查询目标表是否已存在这一天的数据
    select_sql = text(f"SELECT id FROM {table} WHERE {ts_field} = :ts LIMIT 1")
    with engine.connect() as conn:
        result = conn.execute(select_sql, {"ts": ts}).fetchone()
    if result:
        # 存在则更新
        update_sql = text(f"""
            UPDATE {table}
            SET {close_field} = :close, updated_at = :now
            WHERE {ts_field} = :ts
        """)
        with engine.begin() as conn:
            conn.execute(update_sql, {"close": close, "ts": ts, "now": now_str})
        print("已更新目标表 stocks！")
    else:
        # 不存在则插入
        insert_sql = text(f"""
            INSERT INTO {table} ({close_field}, {ts_field}, created_at, updated_at)
            VALUES (:close, :ts, :now, :now)
        """)
        with engine.begin() as conn:
            conn.execute(insert_sql, {"close": close, "ts": ts, "now": now_str})
        print("已插入目标表 stocks！")

if __name__ == "__main__":
    # 源库连接
    engine_src = create_engine(make_conn_str(DB_CONFIG))
    data = fetch_last_row(engine_src, TABLE_NAME, DATE_FIELD, DATE_VALUE, SORT_FIELD)
    if not data:
        exit(1)
    close = data['Close']
    ts_utc = data['Timestamp']
    ts_china_0 = to_china_0am_timestamp(ts_utc)
    print(f"Close: {close}")
    print(f"Timestamp: {ts_china_0}")

    # 目标库连接并插入/更新
    engine_tgt = create_engine(make_conn_str(TARGET_DB_CONFIG))
    insert_or_update(engine_tgt, TARGET_TABLE, TARGET_CLOSE_FIELD, TARGET_TS_FIELD, close, ts_china_0)
