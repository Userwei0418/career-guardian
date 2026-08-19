
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []
    import requests

    url = "https://hr.163.com/api/hr163/position/queryPage"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",

    }
    job_name_to_id = {}
    page_index = 1
    while True:
        payload = {
            "currentPage": page_index,
            "pageSize": 100
        }

        res = requests.post(url, json=payload, headers=headers)
        print(res.json())

        jobs = res.json().get("data", {}).get("list", [])

        for job in jobs:
            job_name_to_id[job["name"]] = job["id"]

        page_index += 1
        if not jobs:
            break
    print(job_name_to_id)
    print(len(job_name_to_id))

    for card in soup.find_all('div', class_='posi-list-card'):
        announcement_name = card.find('span', class_='f-title').get_text(strip=True)
        publish_time = card.find('div', class_='change-show').get_text(strip=True).split(' ')[0]
        if announcement_name in job_name_to_id:
            link = f"https://hr.163.com/job-detail.html?id={job_name_to_id[announcement_name]}&lang=zh"
        else:
            link = ''
        hd_dept = card.find('div', class_='base-detail').get_text(strip=True).split(' ')[0]
        hd_loc = card.find('span', class_='tag f-toe').get_text(strip=True)
        hd_job_num = card.find('div', class_='base-detail').get_text(strip=True).split('人')[0].split()[-1]
        hd_job_category = card.find('div', class_='base-detail').get_text(strip=True).split(' ')[1]
        hd_hope_worktype = ''
        if '实习' in announcement_name:
            hd_hope_worktype = '实习'
        else:
            hd_hope_worktype = ''
        job_list.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category,
            "hd_hope_worktype": hd_hope_worktype
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
