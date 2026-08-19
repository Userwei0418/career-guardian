
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []
    import requests

    api_url = "https://swagger.ecosaas.com/ecosaasbackendlifetime/api/ecosaas/lifetime/career/getPositionInfoPage"

    headers = {
        "User-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"
    }
    job_name_to_id = {}
    payload = {
        "personCode": "null",
        "pageNum": 1,
        "pageSize": 10,
        "sortField": 1,
        "tenantCode": [
            "CDP"
        ],
        "duties": "",
        "dutiesType": [
            ""
        ],
        "jobLocation": "",
        "jobLocationsType": [],
        "activityCode": "1dfe36c81a984013a6cdc8a38ecb7756"
    }

    res = requests.post(api_url, json=payload, headers=headers)
    print(res.json())
    jobs = res.json().get("list", [])

    print(jobs)

    for job in jobs:
        job_name_to_id[job["positionName"]] = job["positionId"]
    print(job_name_to_id)

    companies = soup.find_all('div', class_='company van-cell')
    
    for company in companies:
        job_name = company.find('span', class_='left').text.strip()
        job_info = company.find('div', class_='job-info')
        job_details = job_info.find_all('span', class_='grey-block')
        
        if len(job_details) >= 3:
            publish_time = ""  # Placeholder as the HTML does not provide this information
            if job_name in job_name_to_id:
                link = f"https://m.ecosaas.com/lifetime-h5/#/position-detail?id={job_name_to_id[job_name]}&type=1&clientCode=CDP&activityCode=1dfe36c81a984013a6cdc8a38ecb7756&fromApp=1"
            else:
                link = ""
            hd_dept = ""  # Placeholder as the HTML does not provide this information
            hd_loc = ""
            hd_job_num = ""  # Placeholder as the HTML does not provide this information
            hd_job_category = ""  # Placeholder as the HTML does not provide this information
            
            job_entry = {
                "announcement_name": job_name,
                "publish_time": publish_time,
                "link": link,
                "hd_dept": hd_dept,
                "hd_loc": hd_loc,
                "hd_job_num": hd_job_num,
                "hd_job_category": hd_job_category
            }
            job_list.append(job_entry)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
