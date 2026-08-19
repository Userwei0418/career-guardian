
import json
import time

import requests
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []
    url_api = "https://wecruit.hotjob.cn/wecruit/positionInfo/listPosition/SU66ab2efb1c240e2e76253a76"
    url = "https://wecruit.hotjob.cn/SU66ab2efb1c240e2e76253a76/pb/posDetail.html?postId={post_id}&postType=campus"

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
            "pageSize": 10,
            "coordinateLat": "",
            "coordinateLng": ""
        }

        try:
            resp = requests.post(url_api, headers=headers, params=params)
            data = resp.json()
            positions = data.get("data", {}).get("pageForm", {}).get("pageData", [])
            print(f"第 {page_num} 页职位数:", len(positions))

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

    for card in soup.find_all('div', class_='card-item-wrap'):
        title_div = card.find('div', class_='pos-title-item')
        summary_div = card.find('div', class_='pos-summary')
        footer_div = card.find('div', class_='pos-ft')

        if title_div and summary_div and footer_div:
            announcement_name = title_div.get('title', '').strip()
            publish_time = footer_div.find('span', class_='pub-time').text.replace('发布时间：', '').strip()
            hd_dept = summary_div.contents[0].text.strip()
            hd_job_num = footer_div.find('span', class_='need-people').text.replace('招聘人数：', '').strip()
            hd_loc = summary_div.contents[3].get('title', '').strip()
            hd_job_category = ""
            post_id = id_name_mapping.get(announcement_name)
            if post_id:
                link = url.format(post_id=post_id)

            job_list.append({
                "announcement_name": announcement_name,
                "publish_time": publish_time,
                "link": link,  # Link is not provided in the HTML
                "hd_dept": hd_dept,
                "hd_loc": hd_loc,
                "hd_job_num": hd_job_num,
                "hd_job_category": hd_job_category
            })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
