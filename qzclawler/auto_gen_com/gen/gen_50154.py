
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []
    import requests

    api_url = "https://careers.pddglobalhr.com/api/careers/api/recruit/position/list"
    header = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
        "Content-Type": "application/json"
    }
    job_name_to_id = {}
    page_index = 1
    while True:
        payload = {
            "page": page_index,
            "pageSize": 15,
            "t": "null"
        }
        res = requests.post(api_url, json=payload, headers=header)
        jobs = res.json().get("result", {}).get("list", [])
        if not jobs:
            break
        for job in jobs:
            job_name_to_id[job["name"]] = job["id"]
        page_index += 1

    for card in soup.find_all('div', class_='recruit-card_card__P6WRU'):
        announcement_name = card.find('a', class_='recruit-card_title__yxRoN').get_text(strip=True).replace('紧缺','')
        if announcement_name.endswith("跨境"):
            announcement_name = announcement_name[:-len("跨境")]
        publish_time = card.find_all('span', class_='index_text__BAEBw')[-1].get_text(strip=True)
        if announcement_name in job_name_to_id:
            link = f"https://careers.pddglobalhr.com/campus/grad/detail?positionId={job_name_to_id[announcement_name]}"
        else:
            link = ''
        hd_dept = card.find_all('span', class_='index_text__BAEBw')[0].get_text(strip=True)
        hd_job_category = card.find_all('span', class_='index_text__BAEBw')[1].get_text(strip=True)
        hd_loc = card.find_all('span', class_='index_text__BAEBw')[2].get_text(strip=True)
        hd_job_num = '1'  # Assuming a default value for job number as it's not provided in the HTML

        job_list.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
