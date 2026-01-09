# app.py
from getExpDate import get_valid_contract
from getFuturesData import fetch_data
from mysql import save_to_mysql
import pandas as pd

# ===============================
# 🔹 主程序入口
# ===============================
if __name__ == "__main__":
    print("🔵 正在获取最新有效的期货合约代码...")
    
    # 1️⃣ 从 getExpDate 中获取有效合约代码
    futures_code = get_valid_contract("CKZ24")
    
    if not futures_code:
        print("❌ 无法获取有效的期货合约代码，程序终止。")
        exit(1)

    print(f"✅ 最新有效合约代码: {futures_code}")

    # 2️⃣ 调用 fetch_data 抓取数据
    print(f"🔵 正在抓取 {futures_code} 的期货数据...")
    data = fetch_data(futures_code)

    if data is not None and not data.empty:
        # print(f"✅ 数据抓取成功，前5行如下:")
        # print(data.head())

        # # 3️⃣ 保存为 CSV 文件
        # filename = f"{futures_code}_futures_data.csv"
        # data.to_csv(filename, index=False)
        # print(f"✅ 数据已保存到: {filename}")

        # 4️⃣ 保存到 MySQL
        save_to_mysql(data)
    else:
        print("❌ 数据抓取失败，未生成 CSV 文件。")
