
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []
    import requests

    api_url = "https://gcsservices.careers.microsoft.com/search/api/v1/search"

    headers = {
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
        "referer": "https://jobs.careers.microsoft.com/"
    }
    page_index = 1
    job_name_to_id = {}
    while True:
        payload = {

            "l": "en_us",
            "pg": page_index,
            "pgSz": 150,
            "o": "Relevance",
            "flt": "true"
        }

        res = requests.get(api_url, params=payload, headers=headers)

        jobs = res.json().get("operationResult", {}).get("result", []).get("jobs", [])

        for job in jobs:
            job_name_to_id[job["title"]] = job["jobId"]
        page_index += 1
        if not jobs:
            break
    print(len(job_name_to_id))

    job_cells = soup.find_all('div', class_='ms-List-cell')

    for job in job_cells:
        # 职位名称
        h2_tag = job.find('h2')
        announcement_name = h2_tag.get_text(strip=True) if h2_tag else ""

        # 发布时间（这里你写死 'Today'，其实应该找时间字段，如果找不到就空
        publish_time =   ""

        # 链接按钮
        if announcement_name in job_name_to_id:
            link = f"https://jobs.careers.microsoft.com/global/en/job/{job_name_to_id[announcement_name]}"
        else:
            link = ""
        # 部门信息暂缺
        hd_dept = ""

        # 地点
        loc_span = job.find('span', class_='css-519')
        hd_loc = loc_span.get_text(strip=True) if loc_span else ""

        # 其他信息占位
        hd_job_num = ""
        hd_job_category = ""

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
