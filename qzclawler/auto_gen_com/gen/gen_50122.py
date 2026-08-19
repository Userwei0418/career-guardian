
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    import time

    import requests

    api_url = "https://talent.hikvision.com/api/ats/official/officialPostPosition/getPostInfoForSys"

    headers = {
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.90 Safari/537.36",
        "referer": "https://talent.hikvision.com/society/index",

    }
    page_index = 1
    job_name_to_id = {}
    while True:
        payload = {
            "pageNum": page_index,
            "pageSize": 50,
            "companyId": "",
            "postName": "",
            "proCitys": "",
            "locationDesc": ""
        }

        res = requests.post(api_url, json=payload, headers=headers)

        jobs = res.json().get("data", []).get("list", [])

        print(jobs)

        totle = res.json().get("data", {}).get("total", 0)
        for job in jobs:
            job_name_to_id[job["postName"]] = job["postSecureId"]

        print(job_name_to_id)

        page_index += 1
        time.sleep(0.3)
        if page_index > (totle // 50) + 1:
            break
    print(len(job_name_to_id))
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    table_rows = soup.select('table.el-table__body tbody tr')
    
    data_list = []

    for row in table_rows:
        cells = row.find_all('td')
        if len(cells) < 5:
            continue
        
        announcement_name = cells[0].get_text(strip=True).replace("NEW", "")
        hd_job_category = cells[1].get_text(strip=True)
        hd_loc = cells[2].get_text(strip=True)
        publish_time = cells[3].get_text(strip=True)

        if announcement_name in job_name_to_id:
            job_id = job_name_to_id[announcement_name]
            link = f"https://talent.hikvision.com/society/position?postId={job_id}"
        else:
            link = ""
        
        data_entry = {
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": "",
            "hd_loc": hd_loc,
            "hd_job_num": "",  # Placeholder as the job number is not provided in the HTML
            "hd_job_category": hd_job_category  # Placeholder as the job category is not provided in the HTML
        }
        
        data_list.append(data_entry)
    
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(data_list, f, ensure_ascii=False, indent=4)
