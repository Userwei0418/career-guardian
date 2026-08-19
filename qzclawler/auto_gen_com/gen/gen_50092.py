import json
from contextlib import nullcontext

from bs4 import BeautifulSoup


def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    data_list = []
    import requests
    import time

    url = "https://wecruit.hotjob.cn/wecruit/positionInfo/listPosition/SU61385cb9bef57c3b6383ec61"

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json, text/plain, */*",
    }

    id_name_mapping = {}
    page_num = 1

    while True:
        params = {
            "isAjax": "true",
            "request_locale": "zh_CN",
            "recruitType": 1,
            "currentPage": page_num,
            "pageSize": 100,
            "coordinateLat": "",
            "coordinateLng": ""
        }

        try:
            resp = requests.post(url, headers=headers, params=params)
            data = resp.json()
            positions = data.get("data", {}).get("pageForm", {}).get("pageData", [])

            if not positions:
                print(f"第 {page_num} 页没有职位数据")
                break

            for pos in positions:
                pos_name = pos.get("postName")
                pos_id = pos.get("postId")
                if pos_name and pos_id:
                    id_name_mapping[pos_name] = pos_id

            total_pages = data.get("data", {}).get("pageForm", {}).get("totalPage", 1)
            if page_num >= total_pages:
                break

            page_num += 1
            time.sleep(0.2)

        except requests.RequestException as e:
            print(f"请求页 {page_num} 出错:", e)
            break

    print("岗位名 -> ID 映射:", id_name_mapping)
    print("总数:", len(id_name_mapping))

    items = soup.find_all('div', class_='listItemRt')
    for item in items:
        announcement_name = item.find('span', class_='listItemRtTitCon').text.strip()
        details = item.find('div', class_='listItemRtMsgs').text.strip().split('i class="split"')
        publish_time = ""

        hd_dept = ""
        hd_loc = ""
        hd_job_num = ""
        hd_job_category = ""

        job_id = None
        for job_title, job_id_m in id_name_mapping.items():
            if job_title == announcement_name:
                job_id = job_id_m
                break
        link = f"https://wecruit.hotjob.cn/SU61385cb9bef57c3b6383ec61/mc/detail?postId={job_id}&recruitType=campus&distance=0"

        data_list.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,  # Assuming link is not provided in the HTML
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(data_list, f, ensure_ascii=False, indent=4)
