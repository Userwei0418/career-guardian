import requests
import urllib3
import json
from bs4 import BeautifulSoup
import time

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def extract_table_from_html(html_content, tempfile):
    """
    1. 先调用 API 获取职位 id -> name 映射（支持多个 positionNatureCode）
    2. 然后解析 HTML，原逻辑不变
    3. 构造 link 使用映射
    4. 保存 JSON 文件
    """
    # --- 先爬 API ---
    url = "https://zhaopin.kuaishou.cn/recruit/e/api/v1/open/positions/simple"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
        "Referer": "https://zhaopin.kuaishou.cn/",
        "Origin": "https://zhaopin.kuaishou.cn"
    }
    position_codes = ["C001", "C002"]
    id_name_mapping = {}

    for code in position_codes:
        page_num = 1
        while True:
            params = {
                "pageNum": page_num,
                "pageSize": 100,
                "positionNatureCode": code,
                "workLocationCode": "domestic",
                "recruitProject": "socialr"
            }

            try:
                resp = requests.get(url, headers=headers, params=params, verify=False)
                data = resp.json()
                positions = data.get("result", {}).get("list", [])

                print(f"正在抓取 {code} 页 {page_num}，本页职位数量：{len(positions)}")

                for pos in positions:
                    pos_id = pos.get("id")
                    name = pos.get("name")
                    if pos_id and name:
                        id_name_mapping[pos_id] = name

                total_pages = data.get("result", {}).get("pages", 1)
                if page_num >= total_pages:
                    print(f"{code} 已抓取完成，共 {total_pages} 页\n")
                    break

                page_num += 1
                time.sleep(0.2)

            except requests.RequestException as e:
                print(f"请求 {code} 页 {page_num} 出错:", e)
                break

    # --- 解析 HTML ---
    soup = BeautifulSoup(html_content, 'html.parser')
    table_rows = soup.select('tbody.ant-table-tbody tr')

    data_list = []

    for row in table_rows:
        cols = row.find_all('td')
        if len(cols) >= 5:
            announcement_name = cols[0].get_text(strip=True)
            hd_dept = cols[1].get_text(strip=True)
            hd_loc = cols[2].get_text(strip=True)
            hd_job_num = ""
            hd_job_category = cols[1].get_text(strip=True)
            publish_time = cols[4].get_text(strip=True)

            # 根据名称反查 id 并构造 link
            pos_id = None
            for k, v in id_name_mapping.items():
                if v == announcement_name:
                    pos_id = k
                    break

            link = f"https://zhaopin.kuaishou.cn/recruit/e/#/official/social/job-info/{pos_id}" if pos_id else ''

            data_list.append({
                "announcement_name": announcement_name,
                "publish_time": publish_time,
                "link": link,
                "hd_dept": hd_dept,
                "hd_loc": hd_loc,
                "hd_job_num": hd_job_num,
                "hd_job_category": hd_job_category
            })

    # --- 保存结果 ---
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(data_list, f, ensure_ascii=False, indent=4)

    return data_list

# --- 使用示例 ---
# html_content = "<html>你的HTML内容</html>"
# res = extract_table_from_html(html_content, "output.json")
