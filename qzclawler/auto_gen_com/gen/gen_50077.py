import requests
import urllib3
import json
import time
from bs4 import BeautifulSoup

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def extract_table_from_html(html_content, tempfile):
    """
    一步完成：
    1. 调用 API 获取职位 id -> name 映射
    2. 解析 HTML
    3. 构造 link 字段
    4. 保存 JSON 文件
    """
    # --- 获取职位id与名称映射 ---
    url = "https://campus.kuaishou.cn/recruit/campus/e/api/v1/open/positions/simple"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
        "Content-Type": "application/json",
        "Referer": "https://campus.kuaishou.cn/recruit/campus/e/",
        "Cookie": "apdid=68a386f1-0218-4778-b8dc-47e06e96e9750d31cc7cfaa37cde599c462da62f3fe8:1755765404:1; _did=web_40794163599628D6; aliyungf_tc=f8d1038b7d532900972e311531afa50debf24918b417a18d8f5b3d87f200bad6; accessproxy_session=dcc40a7b-7ae2-4dd1-8d59-4f0a3ad635dd"
    }

    id_name_mapping = {}
    page_num = 1
    page_size = 20

    while True:
        payload = {
            "pageNum": page_num,
            "pageSize": page_size,
            "positionNatureCode": "fulltime",
            "recruitSubProjectCodes": ["20261707035672", "20261749721165"]
        }

        try:
            resp = requests.post(url, json=payload, headers=headers, verify=False, timeout=10)
            resp.raise_for_status()
            data = resp.json()
        except (requests.RequestException, ValueError) as e:
            time.sleep(2)
            continue

        positions = data.get('result', {}).get('list', [])
        if not positions:
            break

        for pos in positions:
            id_name_mapping[pos['id']] = pos.get('name', '')

        if not data.get('result', {}).get('hasNextPage'):
            break

        page_num += 1
        time.sleep(0.2)

    # --- 解析 HTML 并构造 link ---
    soup = BeautifulSoup(html_content, 'html.parser')
    items = soup.find_all('div', class_='item')

    result = []

    for item in items:
        name = item.find('div', class_='name').get('title')
        publish_time = item.find('span', class_='update-time').text.replace(' 发布', '')
        hd_loc = item.find('span', class_='work-location').text
        hd_job_category = item.find('span', class_='position-category').text

        # 根据名称反查id
        pos_id = None
        for k, v in id_name_mapping.items():
            if v == name:
                pos_id = k
                break

        link = f"https://campus.kuaishou.cn/recruit/campus/e/#/campus/job-info/{pos_id}" if pos_id else ''

        result.append({
            "announcement_name": name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": '',
            "hd_loc": hd_loc,
            "hd_job_num": '',
            "hd_job_category": hd_job_category
        })

    # --- 保存结果 ---
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=4)

    return result
