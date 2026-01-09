import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime, date

# 请求头及页面模板配置
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/90.0.4430.93 Safari/537.36"
)
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
PAGE_URL_TEMPLATE = "https://www.barchart.com/futures/quotes/{futures}/overview"

def get_expiration_date(contract):
    """
    对指定的合约代码，抓取页面并提取Expiration Date字段，
    返回一个日期对象（如果提取失败则返回 None）。
    """
    url = PAGE_URL_TEMPLATE.format(futures=contract)
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
    except Exception as e:
        print(f"请求 {url} 异常: {e}")
        return None

    if response.status_code != 200:
        print(f"请求 {url} 失败, 状态码: {response.status_code}")
        return None

    soup = BeautifulSoup(response.text, 'html.parser')
    profile_block = soup.find("div", class_="barchart-content-block commodity-profile")
    if not profile_block:
        print("未找到 commodity-profile 区域")
        return None

    rows = profile_block.find_all("div", class_="row item-row")
    expiration_date_str = None
    for row in rows:
        # 注意：这里的查找方式要求 div 的 class 属性包含 "small-5" 和 "column"
        label_div = row.find("div", {"class": "small-5 column"})
        if label_div and "Expiration Date" in label_div.get_text(strip=True):
            # 使用 CSS 选择器匹配包含 small-7 和 column 的标签，忽略其它额外 class（例如 text-right）
            value_div = row.select_one("div.small-7.column")
            if value_div:
                expiration_date_str = value_div.get_text(strip=True)
            break

    if expiration_date_str:
        # 使用正则提取日期部分（支持 MM/DD/YY 或 MM/DD/YYYY 格式）
        match = re.match(r'(\d{1,2}/\d{1,2}/\d{2,4})', expiration_date_str)
        if match:
            date_only = match.group(1)
            try:
                # 优先按 MM/DD/YY 格式解析
                exp_date = datetime.strptime(date_only, "%m/%d/%y").date()
            except ValueError:
                try:
                    exp_date = datetime.strptime(date_only, "%m/%d/%Y").date()
                except ValueError:
                    print(f"日期格式解析失败: {date_only}")
                    return None
            return exp_date
        else:
            print(f"无法从字符串中提取日期，原字符串为: {expiration_date_str}")
            return None
    else:
        print("未找到 'Expiration Date' 对应的内容")
        return None

def increment_contract(contract):
    """
    假设合约代码格式为 "CKZ" + 两位数字，将数字部分递增1，并返回新的合约代码。
    例如："CKZ23" → "CKZ24"
    """
    prefix = contract[:-2]
    try:
        num = int(contract[-2:])
    except Exception as e:
        print(f"合约代码格式错误: {contract}")
        return contract
    new_num = num + 1
    return f"{prefix}{new_num:02d}"

def get_valid_contract(start_contract="CKZ24"):
    """
    从起始合约开始，判断合约是否已经过期。如果当前合约已过期，
    则依次递增合约代码，直到找到第一个有效的合约代码。
    返回最终有效的合约代码。
    """
    current_contract = start_contract
    while True:
        exp_date = get_expiration_date(current_contract)
        if exp_date is None:
            # 如果无法获取到期日，视为该合约有效（避免无限循环），并直接返回
            print(f"无法获取 {current_contract} 的到期日，假定该合约有效")
            return current_contract

        today = date.today()
        if today >= exp_date:
            print(f"{current_contract} 已经过期, 到期日: {exp_date}, 当前日期: {today}")
            current_contract = increment_contract(current_contract)
        else:
            print(f"{current_contract} 有效, 到期日: {exp_date}, 当前日期: {today}")
            return current_contract

if __name__ == "__main__":
    # 测试：从 "CKZ23" 开始，获取最新有效合约
    valid_contract = get_valid_contract("CKZ24")
    print("最终有效合约:", valid_contract)
