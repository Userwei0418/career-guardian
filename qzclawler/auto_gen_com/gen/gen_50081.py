import requests
import urllib3
import time
import json
from bs4 import BeautifulSoup

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def extract_table_from_html(htmlcontext, tempfile):
    """
    获取 Lenovo 招聘职位信息，构造详情链接，并解析 HTML，最终保存 JSON。

    :param html_content: 本地 HTML 内容或字符串
    :param output_file: 输出 JSON 文件路径
    """
    # 1. Lenovo API 配置
    api_url = "https://talent.lenovo.com.cn/gateway/jobBase/list"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
        "Referer": "https://talent.lenovo.com.cn/position",
        "Accept": "application/json, text/plain, */*",
        "Cookie": "LA_F_T_10000263=1755834749414; LA_C_Id=_ck25082211522914384929558471372; LA_R_T_10000263=1755834749414; LA_M_W_10000263=_ck25082211522914384929558471372%7C10000263%7C%7C%7C; LA_C_C_Id=_sk202508220359380.83535200.5094; LA_V_T_10000263=1755841621682"
    }

    # 2. 获取 API 数据
    id_name_mapping = {}
    page_num = 1
    while True:
        params = {"pageNum": page_num, "pageSize": 100}
        try:
            resp = requests.get(api_url, headers=headers, params=params, verify=False)
            data = resp.json()
            positions = data.get("result", {}).get("rows", [])
            if not positions:
                break
            for pos in positions:
                pos_id = pos.get("id")
                name = pos.get("jobName")
                if pos_id and name:
                    id_name_mapping[pos_id] = name
            total_pages = data.get("result", {}).get("pages", 1)
            if page_num >= total_pages:
                break
            page_num += 1
            time.sleep(0.2)
        except requests.RequestException as e:
            print(f"请求页 {page_num} 出错:", e)
            break

    print(f"获取到 {len(id_name_mapping)} 个职位信息")

    # 3. 解析 HTML
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    items = soup.find_all('div', class_='list_item')
    result = []

    for item in items:
        title_div = item.find('div', class_='list_item_title')
        type_div = item.find('div', class_='list_item_type')
        map_div = item.find('div', class_='list_item_map')

        announcement_name = title_div.find('span').text.strip()

        # 构造 link
        pos_id = None
        for k, v in id_name_mapping.items():
            if v == announcement_name:
                pos_id = k
                break
        link = f"https://talent.lenovo.com.cn/position/detail?id={pos_id}" if pos_id else ""

        publish_time = ""
        hd_dept = type_div.find_all('span')[-1].text.strip()
        hd_loc = map_div.find('span').text.replace('工作地点：', '').strip()
        hd_job_num = ""
        hd_job_category = type_div.find_all('span')[2].text.strip()

        result.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        })

    # 4. 保存 JSON
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=4)



