
import json
import time

import requests
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",

    }
    url = "https://api.geelytech.com/console-gateway/zp-api/internal/website/positions"
    job_name_to_id = {}
    page_index = 1
    while True:
        data = {
            "keyword": '',
            "pageNo": page_index,
            "pageSize": "50",
            "timeStamp": "-1"
        }

        response = requests.get(url, headers=headers, data=data)

        res = response.json()
        positions = res.get("data", {})
        jobs = positions.get("data", [])
        total = positions.get("totalSize", 0)
        for job in jobs:
            job_name_to_id[job['title']] = job['id']
        page_index += 1
        for positions in positions.get('positions', []):
            job_name_to_id[positions['positions']['title']] = positions['id']
        if page_index > (total // 50) + 1:
            time.sleep(1)
            break


    for position in soup.find_all('div', class_='style__position_1ECz9'):
        titles = position.h3.get_text(strip=True).split(' ')
        title = ""
        if len(titles) >= 3:
            title = titles[2]
        details = position.h4.get_text(strip=True).split('|')
        if title in job_name_to_id:
            id = job_name_to_id[title]
            link = f"https://careers.geelytech.com/position/{id}"
        else:
            link = ""

        if len(details) >= 4:
            announcement_name = title
            hd_dept = details[0].strip()
            hd_loc = details[1].strip()
            hd_job_category = details[2].strip()
            publish_time = details[3].strip()
            hd_job_num = ""  # Assuming job number is not provided in the HTML

            job_list.append({
                "announcement_name": announcement_name,
                "publish_time": publish_time,
                "link": link,  # Assuming no link is provided in the HTML
                "hd_dept": hd_dept,
                "hd_loc": hd_loc,
                "hd_job_num": hd_job_num,
                "hd_job_category": hd_job_category
            })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
