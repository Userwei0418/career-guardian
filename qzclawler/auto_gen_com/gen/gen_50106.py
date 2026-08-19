import json
from bs4 import BeautifulSoup


def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    positions = []
    import requests
    import time

    url = "https://career.cmbchina.com/api/socialRecruitmentWebsite/job/getList"

    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
        "Origin": "https://career.cmbchina.com",
        "Referer": "https://career.cmbchina.com/positionlist/48E013CF-A9DE-4FA4-9CEE-4967B162CAEF",
        "Cookie": "$initData={%22startTime%22:1756797782404%2C%22hasToJobDetailSchool%22:false%2C%22hasToJobDetailSocial%22:true}; processID1=17567997220909319.234261250185; processID2=17567997272831600.760712682796"
    }

    job_map = {}  # 用来存 jobDisplay -> location 的映射
    page = 1
    page_size = 50

    while True:
        payload = {
            "orgIdList": [],
            "keywords": "",
            "locationIdList": [],
            "pageIndex": page,
            "pageSize": page_size,
            "jobTypeIdList": []
        }

        resp = requests.post(url, json=payload, headers=headers)
        if resp.status_code != 200:
            print(f"请求失败: {resp.status_code}")
            break

        data = resp.json()
        # 注意结构要确认，有的是 data.get("info", {}).get("records", [])
        records = data.get("body", {}).get("data", [])
        if not records:
            print("没有更多数据，抓取结束。")
            break

        for job in records:
            job_name = job.get("jobDisplay")
            job_loc = job.get("publishGID")
            print(job_name, "-", job_loc)
            if job_name:
                job_map[job_name] = job_loc

        page += 1
        time.sleep(1)
    print(job_map)

    for item in soup.find_all('div', class_='position-item'):
        title = item.find('div', class_='title').text.strip()
        details = item.find('div', class_='deatil').find_all('span')

        if len(details) >= 3:
            hd_dept = details[0].text.strip()
            hd_loc = details[2].text.strip()
            hd_job_category =details[1].text.strip()
        else:
            hd_dept = hd_loc = hd_job_category = ""
        link = ""
        for k ,v in job_map.items():
            if k == title:
                job_id = v
                link = f"https://career.cmbchina.com/positionDetail/social?publishId={job_id}"
                break

        position = {
            "announcement_name": title,
            "publish_time": "2025-08-18",
            "link": link,  # Assuming no link is provided in the HTML
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": "",  # Assuming no job number is provided in the HTML
            "hd_job_category": hd_job_category
        }

        positions.append(position)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(positions, f, ensure_ascii=False, indent=4)


