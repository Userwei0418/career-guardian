
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []
    import requests

    api_url = "https://campus.pingan.com/zztj-recruit-talent-webserver/rctt/candidate/position/campus/positionSearch/queryPositionPage"

    headers = {
        "User-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
        "referer": "https://campus.pingan.com/tech/position",
        "accept": "application/json;charset=utf-8"
    }
    job_name_to_ids = {}

    payload = {
        "PageNum": 1,
        "businessUnitId": "",
        "pageSize": 50,
        "positionCategoryId": "",
        "wecruitId": "281a0da7b01430f3be271b436eff03ce",
        "positionType": "",
        "wecruitPlatform": "true",
        "workCity": "",
        "interviewCity": ""
    }

    res = requests.post(api_url, json=payload, headers=headers)
    print(res.json())

    jobs = res.json().get("data", {}).get("list", [])

    for job in jobs:
        job_name_to_ids[job["positionName"]] = job["idPosition"]

    print(job_name_to_ids)
    print(len(job_name_to_ids))

    for card in soup.find_all(class_='card-wrapper'):
        announcement_name = card.find(class_='name').text.strip() if card.find(class_='name') else ""
        hd_dept =  ""
        hd_loc = card.find(class_='work-city').find_all('span')[1].text.strip() if card.find(class_='work-city') else ""
        hd_job_category = card.find(class_='type').text.strip() if card.find(class_='type') else ""
        
        # Placeholder values for missing fields
        publish_time = ""
        if announcement_name in job_name_to_ids:
            link = f"https://campus.pingan.com/tech/positionDetail?positionId={job_name_to_ids[announcement_name]}"
        else:
            link = ""
        hd_job_num = ""
        
        job_info = {
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        }
        
        job_list.append(job_info)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
