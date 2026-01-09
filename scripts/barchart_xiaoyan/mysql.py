# mysql.py
from sqlalchemy import create_engine, text
import pandas as pd

# ===============================
# 🔹 MySQL 配置信息
# ===============================
DB_CONFIG = {
    'user': 'barchart',
    'password': 'Ni48dG225dNMW7cR',
    'host': 'localhost',
    'port': 3306,
    'database': 'barchart'
}

# 构建数据库连接 URI
DB_URI = f"mysql+pymysql://{DB_CONFIG['user']}:{DB_CONFIG['password']}@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}?charset=utf8mb4"

# 建立数据库引擎
engine = create_engine(DB_URI)

# ===============================
# 🔹 初始化数据库表
# ===============================
def initialize_table():
    """
    如果数据表 barchart 不存在，创建表并设置唯一索引
    """
    create_table_sql = text("""
    CREATE TABLE IF NOT EXISTS `barchart` (
        `Timestamp` BIGINT NOT NULL,
        `Date` DATE NOT NULL,
        `Time` TIME NOT NULL,
        `Open` FLOAT,
        `High` FLOAT,
        `Low` FLOAT,
        `Close` FLOAT,
        `Volume` INT,
        PRIMARY KEY (`Timestamp`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)
    
    with engine.connect() as conn:
        conn.execute(create_table_sql)
        print(f"✅ 数据表 `barchart` 初始化完成")


# ===============================
# 🔹 批量插入数据（批次 500 条）
# ===============================
def save_to_mysql(df: pd.DataFrame, batch_size=500):
    """
    保存 DataFrame 到 MySQL，并避免重复插入
    """
    try:
        print(f"🟢 开始保存数据到 MySQL 表 `barchart`...")

        # 1️⃣ 初始化表（如果不存在）
        initialize_table()

        # 2️⃣ 构建批量插入数据
        insert_sql = text("""
        INSERT IGNORE INTO `barchart` (`Timestamp`, `Date`, `Time`, `Open`, `High`, `Low`, `Close`, `Volume`) 
        VALUES (:Timestamp, :Date, :Time, :Open, :High, :Low, :Close, :Volume)
        """)

        # 3️⃣ 修正数据格式：把时间对象转成字符串
        data_tuples = [
            {
                "Timestamp": row.Timestamp,
                "Date": row.Date.strftime('%Y-%m-%d'),
                "Time": row.Time.strftime('%H:%M:%S'),
                "Open": row.Open,
                "High": row.High,
                "Low": row.Low,
                "Close": row.Close,
                "Volume": row.Volume
            }
            for row in df.itertuples(index=False)
        ]

        total_inserted = 0

        # 4️⃣ 分批次插入，每次 500 条
        with engine.connect() as conn:
            transaction = conn.begin()
            try:
                for i in range(0, len(data_tuples), batch_size):
                    batch = data_tuples[i:i + batch_size]
                    result = conn.execute(insert_sql, batch)
                    print(f"✅ 成功插入 {result.rowcount} 条记录")
                    total_inserted += result.rowcount
                transaction.commit()
                print(f"✅ 批量插入完成，共成功插入 {total_inserted} 条记录")
            except Exception as e:
                transaction.rollback()
                print(f"❌ 批量插入失败，事务回滚: {e}")
                print("❌ 本次插入 **未保存** 到数据库")
                return

        print(f"✅ 数据成功保存到 MySQL -> `barchart`，总共插入 {total_inserted} 条记录")
    except Exception as e:
        print(f"❌ 数据库写入失败: {e}")
