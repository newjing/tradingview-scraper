import argparse
import json
import os
import time
from datetime import datetime
from io import StringIO

import pandas as pd
import requests
from seleniumwire import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

# Jing  尝试，网络不成功，发现直接到 barchart 里找devtool network queryeod.ashx 链接的response复制过来更简单
def _trigger_chart_request(driver):
    selectors = [
        "canvas",
        ".bc-interactive-chart",
        ".chart-container",
        ".highcharts-container",
        ".chart-wrapper",
    ]
    for selector in selectors:
        try:
            element = driver.find_element(By.CSS_SELECTOR, selector)
            ActionChains(driver).move_to_element(element).click().perform()
            return True
        except Exception:
            continue

    try:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight / 2);")
        driver.execute_script(
            """
            const el = document.elementFromPoint(window.innerWidth / 2, window.innerHeight / 2);
            if (el) {
              el.dispatchEvent(new MouseEvent('mousemove', { bubbles: true }));
              el.dispatchEvent(new MouseEvent('click', { bubbles: true }));
            } else {
              document.body.click();
            }
            """
        )
        return True
    except Exception:
        return False


def get_request_headers(symbol, timeout_sec=60, poll_interval=1):
    """Use Selenium Wire to capture request headers for Barchart time series."""
    print(f"Starting browser to capture headers for {symbol}...")
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("window-size=1920x1080")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/113.0.0.0 Safari/537.36"
    )

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    try:
        url = f"https://www.barchart.com/futures/quotes/{symbol}/interactive-chart"
        driver.get(url)
        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        for attempt in range(2):
            try:
                request = driver.wait_for_request("queryminutes.ashx", timeout=timeout_sec)
                headers = {header: value for header, value in request.headers.items()}
                return headers
            except Exception:
                deadline = time.time() + timeout_sec
                while time.time() < deadline:
                    for request in driver.requests:
                        if "queryminutes.ashx" in request.url:
                            headers = {header: value for header, value in request.headers.items()}
                            return headers
                    time.sleep(poll_interval)

            if attempt == 0:
                print("queryminutes.ashx not found, triggering interaction and refreshing...")
                _trigger_chart_request(driver)
                try:
                    driver.requests.clear()
                except Exception:
                    pass
                driver.refresh()
                _trigger_chart_request(driver)

        print("queryminutes.ashx request not found within timeout.")
        return None
    finally:
        driver.quit()


def fetch_5m_data(symbol, max_records=1205):
    """Fetch 5-minute data from Barchart and return a DataFrame."""
    headers = get_request_headers(symbol)
    if not headers:
        print("Failed to capture headers.")
        return None

    url = "https://www.barchart.com/proxies/timeseries/historical/queryminutes.ashx"
    params = {
        "symbol": symbol,
        "maxrecords": max_records,
        "interval": 5,
        "volume": "contract",
        "order": "asc",
        "dividends": "false",
        "backadjust": "false",
        "daystoexpiration": 1,
        "contractroll": "combined",
    }

    print(f"Requesting 5m data for {symbol}...")
    response = requests.get(url, headers=headers, params=params, timeout=30)
    if response.status_code != 200:
        print(f"Request failed: {response.status_code}")
        print(response.text[:500])
        return None

    csv_data = response.text
    df = pd.read_csv(
        StringIO(csv_data),
        header=None,
        names=["DateTime", "Interval", "Open", "High", "Low", "Close", "Volume"],
        parse_dates=["DateTime"],
    )

    df["Date"] = df["DateTime"].dt.date
    df["Time"] = df["DateTime"].dt.time
    df["Timestamp"] = df.apply(
        lambda row: int(datetime.combine(row["Date"], row["Time"]).timestamp()), axis=1
    )

    return df[["Timestamp", "Date", "Time", "Open", "High", "Low", "Close", "Volume"]]


def save_json(df, output_path):
    """Save a DataFrame to JSON (list of records)."""
    records = df.to_dict(orient="records")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False)


def main():
    parser = argparse.ArgumentParser(description="Fetch 5m futures data from Barchart")
    parser.add_argument("--symbol", default="CKZ25", help="Futures symbol")
    parser.add_argument("--max-records", type=int, default=1205, help="Max records")
    parser.add_argument(
        "--output",
        default=None,
        help="Output JSON path (default: scripts/barchartNew/output/<symbol>_5m.json)",
    )
    args = parser.parse_args()

    output = args.output
    if not output:
        out_dir = os.path.join(os.path.dirname(__file__), "output")
        os.makedirs(out_dir, exist_ok=True)
        output = os.path.join(out_dir, f"{args.symbol}_5m.json")

    data = fetch_5m_data(args.symbol, max_records=args.max_records)
    if data is None or data.empty:
        print("No data fetched.")
        return

    save_json(data, output)
    print(f"Saved JSON to: {output}")


if __name__ == "__main__":
    main()
