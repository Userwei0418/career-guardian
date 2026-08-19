import requests
import time
import urllib3
import json
from bs4 import BeautifulSoup

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def extract_table_from_html(htmlcontext, tempfile):
    # ---------------- 1. 调用 API 获取职位列表 ----------------
    url = "https://utfinancing.zhiye.com/api/Jobad/GetJobAdPageList"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
        "Content-Type": "application/json",
        "Referer": "https://utfinancing.zhiye.com/"
    }
    types = {"campus": 1, "social": 2}
    job_id_map = {}  # 用职位名称或其他唯一字段映射 job_id

    for t_name, t_val in types.items():
        page_index = 0
        while True:
            payload = {
                "PageIndex": page_index,
                "PageSize": 100,
                "Category": t_val,
                "KeyWords": "",
                "SpecialType": "",
                "PortalId": "",
                "recruitType": "",
                "DisplayFields": ["Category", "Kind", "LocId", "Salary", "Degree",
                                  "YearsOfWorking", "ClassificationOne", "ClassificationTwo", "JobAdName", "Id"]
            }
            resp = requests.post(url, json=payload, headers=headers, verify=False)
            jobs = resp.json().get("Data", [])
            if not jobs:
                break
            for job in jobs:
                name = job.get("JobAdName")
                job_id = job.get("Id")
                if name and job_id:
                    job_id_map[name] = job_id
            page_index += 1
            time.sleep(0.3)

    # ---------------- 2. 原 HTML 解析逻辑 ----------------
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for item in soup.find_all("div", class_="style__STListItem-editor__sc-10r1nhd-0"):
        title = item.find("div", class_="style__STJobTitle-editor__sc-10r1nhd-4").get_text(strip=True)
        publish_time = item.find("div", class_="style__STJobTime-editor__sc-10r1nhd-16").get_text(strip=True).replace(" 发布", "")
        hd_dept = ""
        hd_loc = item.find_all("div", class_="style__STLabelText-editor__sc-10r1nhd-13")[-1].get_text(strip=True)
        hd_job_num = ""  # 保留原业务占位
        hd_job_category = ""  # 保留原业务占位

        # ---------------- 构造 link ----------------
        job_id = job_id_map.get(title, "")
        link = f"https://utfinancing.zhiye.com/social/detail?jobAdId={job_id}" if job_id else ""

        job_list.append({
            "announcement_name": title,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)

    print(f"总共抓取职位数: {len(job_list)}")
