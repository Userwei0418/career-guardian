
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []
    import requests
    import time
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    url = "https://career.h3c.com/api/Jobad/GetJobAdPageList"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
        "Content-Type": "application/json",
        "Referer": "https://career.h3c.com/"
    }

    types = {
        "campus": 2,
        "social": 1,
        "intern": 3
    }

    all_jobs = []
    job_name_to_id = {}
    for t_name, t_val in types.items():
        print(f"抓取 {t_name} 招聘...")
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
                                  "YearsOfWorking", "ClassificationOne", "ClassificationTwo"]
            }
            resp = requests.post(url, json=payload, headers=headers, verify=False)
            jobs = resp.json().get("Data", [])
            if not jobs:
                break
            # 给每条数据加上类型字段，方便后面区分
            for job in jobs:
                job["job_type"] = t_name
            all_jobs.extend(jobs)
            print(f"  Page {page_index} done, got {len(jobs)} jobs")
            page_index += 1
            time.sleep(0.3)

            for job in all_jobs:
                name = job.get("JobAdName")  # 根据接口字段调整
                job_id = job.get("Id")
                if name and job_id:
                    job_name_to_id[name] = job_id

            print(job_name_to_id)

    print(f"总共抓取职位数: {len(all_jobs)}")

    for item in soup.find_all("div", class_="style__STListItem-editor__sc-10r1nhd-0"):
        title = item.find("div", class_="style__STJobTitle-editor__sc-10r1nhd-4").get_text(strip=True)
        publish_time = item.find("div", class_="style__STJobTime-editor__sc-10r1nhd-16").get_text(strip=True).replace(" 发布", "")
        jobad_id = None
        link = ""
        for N, I in job_name_to_id.items():
            if title.strip() == N.strip():
                jobad_id = I
                link = f"https://career.h3c.com/social/detail?jobAdId={jobad_id}"
                break
        lables = item.find_all("div" , class_= "style__STJobLabel-editor__sc-10r1nhd-12")
        for lbs in lables:
            text = lbs.get_text(strip=True)
            if "省" in text or "市" in text or "区" in text:
                hd_loc = text
            else:
                hd_type = text
        hd_job_category = ""

        hd_dept = ""
        hd_job_num = "1"  # Placeholder for actual job number extraction

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
