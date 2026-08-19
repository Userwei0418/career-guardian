
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []
    import requests

    session = requests.Session()

    # 第一步：访问页面获取 Cookie 和 _csrf
    page = session.get("https://careers.aliyun.com/off-campus/position-list?lang=zh")
    # 假设从 HTML 或 Cookie 中解析出 _csrf
    csrf_token = session.cookies.get("XSRF-TOKEN")  # 常见存放位置

    # 第二步：发 POST 请求
    url = f"https://careers.aliyun.com/position/search?_csrf={csrf_token}"
    page_index = 1
    job_name_to_id = {}
    while True:
        payload = {
            "channel": "group_official_site",
            "language": "zh",
            "batchId": "",
            "categories": "",
            "deptCodes": [],
            "key": "",
            "pageIndex": page_index,
            "pageSize": 150,
            "regions": "",
            "subCategories": ""
        }

        headers = {
            "User-Agent": "Mozilla/5.0 ...",
            "Referer": "https://careers.aliyun.com/off-campus/position-list?lang=zh",
            "Content-Type": "application/json"
        }

        res = session.post(url, json=payload, headers=headers)
        jobs = res.json().get("content", []).get("datas", [])

        for job in jobs:
            job_name_to_id[job["name"]] = job["id"]

        page_index += 1
        if page_index > 10:
            break

    job_elements = soup.find_all('div', class_='_2AOmjKmlEtuR_KEoehWYcN')
    
    for job in job_elements:
        announcement_name = job.find('div', class_='_1RRlPtjyYmeDGCWt9lrk2P').text.strip()
        publish_time = job.find('div', class_='_3Jn5Z6PZA5H7Auzy0xlXu2').text.replace('更新于 ', '').strip()
        hd_loc = job.find('div', class_='_3CJNtKfv5mLnNfeqL1jgRB').text.strip()
        for job_name, job_id in job_name_to_id.items():
            if job_name in announcement_name:
                id = job_id
                link = f"https://careers.aliyun.com/off-campus/position-detail?lang=zh&positionId={id}"
                break
        job_info = {
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,  # Link is not provided in the HTML snippet
            "hd_dept": "",  # Department is not provided in the HTML snippet
            "hd_loc": hd_loc,
            "hd_job_num": "",  # Job number is not provided in the HTML snippet
            "hd_job_category": ""  # Job category is not provided in the HTML snippet
        }
        
        job_list.append(job_info)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
