
import json
from bs4 import BeautifulSoup
from numpy.core.defchararray import title


def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    table_rows = soup.select('.el-table__body .el-table__row')
    
    data_list = []
    import uuid
    import requests

    url = "https://recruit.midea.com/backend/rec/home/out/official/position/list"
    track_id = str(uuid.uuid4())
    full_url = f"{url}?_ihr_log_trackId={track_id}"

    headers = {
        "User-Agent": "Mozilla/5.0",
        # 可能还需要 Cookie 或其他头部
    }
    job_name_to_ids = {}
    page_index = 1
    while True:
        payload = {
            "pageSize": 50,
            "pageIndex": page_index,
            "publicationName": ""
        }

        res = requests.post(full_url, data=payload, headers=headers)
        print(res.json())
        jobs = res.json().get("data", {})
        total = res.json().get("total", 0)

        for job in jobs:
            key = f"{job['demandPositionName']}_{job['workingPlace']}"
            job_name_to_ids[key] = job["positionId"]

        if not jobs or page_index > total // 50 + 1:
            break
        page_index += 1

    print(job_name_to_ids)
    print(len(job_name_to_ids))
    
    for row in table_rows:
        cells = row.find_all('td')
        if len(cells) >= 5:
            announcement_name = cells[0].get_text(strip=True)
            hd_dept = cells[1].get_text(strip=True)
            hd_job_category = cells[2].get_text(strip=True)
            hd_loc = cells[3].get_text(strip=True)
            publish_time = cells[4].get_text(strip=True)
            title = f"{announcement_name}_{hd_loc}"
            print( title)
            # Assuming link is not provided in the given HTML context
            if title in job_name_to_ids:
                link = f"https://recruit.midea.com/recruitOut/ihr/social/jobApplication?positionId={job_name_to_ids[title]}&recruitType=social"
            else:
                link = ""
            # Assuming hd_job_num is not provided in the given HTML context
            hd_job_num = ""
            
            data_list.append({
                "announcement_name": announcement_name,
                "publish_time": publish_time,
                "link": link,
                "hd_dept": hd_dept,
                "hd_loc": hd_loc,
                "hd_job_num": hd_job_num,
                "hd_job_category": hd_job_category
            })
    
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(data_list, f, ensure_ascii=False, indent=4)

