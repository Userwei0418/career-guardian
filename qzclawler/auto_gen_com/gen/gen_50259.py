
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    positions = []
    import requests

    header = {
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
        "referer": "https://campus.gientech.com/"
    }

    job_name_to_id = {}
    page_index = 1
    page_size = 50

    while True:
        payload = {
            "pageNo": page_index,
            "pageSize": page_size,
            "functionType": [],
            "positionType": [],
            "city": [],
            "skill": ""
        }
        api_url = "https://campus.gientech.com/CampusApi/position/selectPostion"
        res = requests.post(api_url, headers=header, json=payload)
        data = res.json()

        body = data.get("body", {})
        lst = body.get("list", [])

        jobs = [pos for item in lst for pos in item.get("positions", [])]

        for job in jobs:
            job_name_to_id[f"{job['name']}_{job['positionNo']}"] = job["id"]

        total = body.get("total", 0)
        total_pages = (total + page_size - 1) // page_size
        print(f"Page {page_index}: {len(jobs)} positions, total collected: {len(job_name_to_id)}")
        print(job_name_to_id)
        page_index += 1
        if page_index > total_pages:
            break

    print("Total jobs collected:", len(job_name_to_id))

    for item in soup.find_all(class_='positionItem'):
        title = item.find(class_='positionItemTitle').text.strip()
        sub_info = item.find(class_='positionItemSub').text.strip().split(' ｜ ')
        desc = item.find(class_='positionItemDesc').text.strip()

        announcement_name = title
        publish_time = ""  # Assuming this information is not present in the HTML

        hd_dept = sub_info[0] if len(sub_info) > 0 else ""
        hd_loc = sub_info[1] if len(sub_info) > 1 else ""
        hd_job_num = sub_info[2] if len(sub_info) > 2 else ""
        hd_job_category = sub_info[3].split('：')[-1] if len(sub_info) > 3 else ""
        prx = f"{title}_{hd_job_category}"
        if prx in job_name_to_id:
            link = f"https://campus.gientech.com/#/positionDetail?id={job_name_to_id[prx]}"
        else:
            link = ""
        position_data = {
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": "",
            "hd_loc": hd_dept,
            "hd_job_num": "",
            "hd_job_category": ""
        }

        positions.append(position_data)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(positions, f, ensure_ascii=False, indent=4)
