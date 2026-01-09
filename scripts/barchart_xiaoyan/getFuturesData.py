from seleniumwire import webdriver
from selenium.webdriver.chrome.options import Options
import time
import requests
import pandas as pd
from io import StringIO
from datetime import datetime

# ===============================
# 🔹 获取最新的 Request Headers
# ===============================
def get_request_headers(futures_code):
    """
    启动 Selenium，访问目标页面，获取 queryeod.ashx 的请求头信息
    """
    print(f"🟢 正在启动 Selenium 浏览器来获取合约 {futures_code} 的请求头...")
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("window-size=1920x1080")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36")

    driver = webdriver.Chrome(options=options)

    try:
        url = f"https://www.barchart.com/futures/quotes/{futures_code}/interactive-chart"
        driver.get(url)
        print("🟢 页面加载成功，等待 10 秒钟让所有请求完成...")
        time.sleep(10)

        # 获取 queryeod.ashx 的请求头
        for request in driver.requests:
            if 'queryeod.ashx' in request.url:
                print("✅ 找到 queryeod.ashx 请求")
                headers = {header: value for header, value in request.headers.items()}
                driver.quit()
                print("🟢 浏览器关闭")
                return headers

        print("🔴 未找到 queryeod.ashx 请求，检查页面是否加载成功。")
        driver.quit()
    except Exception as e:
        print(f"❌ 获取请求头失败: {e}")
        driver.quit()
        return None

# ===============================
# 🔹 发起数据请求并解析
# ===============================
def fetch_data(futures_code):
    """
    从 queryminutes.ashx 接口获取数据并解析为 DataFrame
    """
    # 1️⃣ 获取最新的请求头
    headers = get_request_headers(futures_code)
    if not headers:
        print("❌ 无法获取请求头，程序终止。")
        return
    
    # 2️⃣ 目标接口配置
    url = "https://www.barchart.com/proxies/timeseries/historical/queryminutes.ashx"
    params = {
        'symbol': futures_code,
        'maxrecords': 1205,
        'volume': 'contract',
        'order': 'asc',
        'dividends': 'false',
        'backadjust': 'false',
        'daystoexpiration': 1,
        'contractroll': 'combined'
    }

    try:
        print(f"🟢 正在请求{futures_code}的数据...")
        response = requests.get(url, headers=headers, params=params)

        # 3️⃣ 检查请求状态
        print(f"📝 状态码: {response.status_code}")
        if response.status_code != 200:
            print("❌ 请求失败，返回内容：")
            print(response.text[:500])
            return

        # 4️⃣ 解析 CSV 格式数据
        csv_data = response.text
        print("🟢 正在解析 CSV 数据...")
        
        # 直接在读取的时候解析 'DateTime' 为两列：'Date' 和 'Time'
        df = pd.read_csv(
            StringIO(csv_data), 
            header=None, 
            names=['DateTime', 'Interval', 'Open', 'High', 'Low', 'Close', 'Volume'],
            parse_dates=['DateTime']
        )
        
        # 直接将 'DateTime' 分解为 'Date' 和 'Time'
        df['Date'] = df['DateTime'].dt.date
        df['Time'] = df['DateTime'].dt.time
        
        # 生成 `timestamp` 列
        df['Timestamp'] = df.apply(lambda row: int(datetime.combine(row['Date'], row['Time']).timestamp()), axis=1)
        
        # 删除多余的 'DateTime' 和 'Interval'
        df = df[['Timestamp', 'Date', 'Time', 'Open', 'High', 'Low', 'Close', 'Volume']]
        
        # 5️⃣ 打印结果
        # print("\n✅ 数据解析成功，前5行如下:")
        # print(df.head())
        return df

    except requests.RequestException as e:
        print(f"❌ 请求失败: {e}")
        return None

# ===============================
# 🔹 主程序入口
# ===============================
if __name__ == "__main__":
    # 这里可以改成你要抓取的合约代码
    contract_code = "CKZ25"
    print(f"🔵 开始获取 {contract_code} 的数据...")
    
    data = fetch_data(contract_code)
    if data is not None:
        print("✅ 数据抓取完成。")
    else:
        print("❌ 数据抓取失败。")
