import json
import requests
import time
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    # -------------------- 1. 构建岗位映射表（仅 jobId → title 用于 link） --------------------
    url = "https://careers.shein.cn/api/v1/open/grw/front/jobPage"
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
        "Origin": "https://careers.shein.cn",
        "Referer": "https://careers.shein.cn/All-Jobs",
        "Cookie": "Hm_lvt_ce2f789e167400acd61b5780948e2dd1=1755575616,1755671697,1756361775; HMACCOUNT=F81187572CDA47C7; Hm_lpvt_ce2f789e167400acd61b5780948e2dd1=1756362720"
    }

    job_type_map = {
        "campus": ["CAMPUS", "PRACTICE"],
        "social": ["SOCIAL"]
    }

    job_map = {}
    for job_type_name, job_type_ids in job_type_map.items():
        page = 1
        page_size = 20

        while True:
            payload = {
                "current": page,
                "cityName": "",
                "jobCategoryIds": [],
                "cityIds": [],
                "jobTypeIds": job_type_ids,
                "key": "",
                "langCode": "CN",
                "size": page_size
            }

            resp = requests.post(url, json=payload, headers=headers)
            if resp.status_code != 200:
                break

            data = resp.json()
            records = data.get("info", {}).get("records", [])
            if not records:
                break

            for job in records:
                job_title = job.get("jobTitle")
                job_map[job_title] = job.get("jobId")  # 只存 title，用于匹配生成 link

            page += 1
            time.sleep(0.5)

    # -------------------- 2. 解析 HTML --------------------
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_listings = []

    for listing in soup.find_all('div', class_='lists'):
        announcement_name = listing.h3.contents[0].strip()
        publish_time = ""
        hd_dept = ""
        cities = []
        for city_ol in listing.select('ol.cityItems'):
            for li in city_ol.select('li.lab'):
                cities.append(li.get_text(strip=True))
        hd_loc = ', '.join(cities)
        hd_job_category = listing.find('li', class_='lab word f-16').get_text(strip=True)
        hd_job_num = ""

        # 只构造 link，不需要分类
        job_id = None
        for title, jid in job_map.items():
            if title == announcement_name:
                job_id = jid
                break
        link = f"https://app.mokahr.com/campus-recruitment/shein/2932#/job/{job_id}" if job_id else ""

        job_listings.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        })

    # -------------------- 3. 写入 JSON --------------------
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_listings, f, ensure_ascii=False, indent=4)
