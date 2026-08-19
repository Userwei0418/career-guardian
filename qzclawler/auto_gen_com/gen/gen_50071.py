import requests
import time
import urllib3
import json
from bs4 import BeautifulSoup
from collections import defaultdict

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def extract_table_from_html(htmlcontext, tempfile):
    """
    解析 HTML 职位列表并结合 API 构造职位详情链接，
    最终保存为 JSON 文件。
    """
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    # ===== 调用 API 获取职位映射 =====
    url = "https://gaush.zhiye.com/api/Jobad/GetJobAdPageList"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
        "Content-Type": "application/json",
        "Referer": "https://gaush.zhiye.com/"
    }
    types = {
        "campus": 1,
        "social": 2,
        "intern": 3
    }

    all_jobs = []

    for t_name, t_val in types.items():
        page_index = 0
        while True:
            payload = {
                "PageIndex": page_index,
                "PageSize": 100,
                "Category": t_val,
                "KeyWords": "",
                "SpecialType": 0,
                "PortalId": "",
                "recruitType": "",
                "DisplayFields": ["Category", "Kind", "LocId", "Salary", "Degree",
                                  "YearsOfWorking", "ClassificationOne", "ClassificationTwo"]
            }
            resp = requests.post(url, json=payload, headers=headers, verify=False)
            try:
                jobs = resp.json().get("Data", [])
            except Exception:
                break  # JSON 解析失败就跳出

            if not jobs:
                break

            for job in jobs:
                job["job_type"] = t_name
            all_jobs.extend(jobs)

            page_index += 1
            time.sleep(0.2)

    # ===== 构建职位名映射 JobName -> Id =====
    job_name_to_id = {}
    for job in all_jobs:
        name = job.get("JobAdName") or job.get("JobName")  # 根据实际字段
        job_id = job.get("Id") or job.get("JobAdId")
        post_type = job.get("job_type")
        if name and job_id:
            job_name_to_id[name] = {"postId": job_id, "postType": post_type}

    # ===== 解析 HTML 列表 =====
    for item in soup.find_all("div", class_="style__STListItem-editor__sc-10r1nhd-0"):
        announcement_name = item.find("div", class_="style__STJobTitle-editor__sc-10r1nhd-4").get_text(strip=True)
        publish_time = item.find("div", class_="style__STJobTime-editor__sc-10r1nhd-16").get_text(strip=True).replace(" 发布", "")

        # 提取标签信息
        labels = item.find_all("div", class_="style__STLabelText-editor__sc-10r1nhd-13 cJYhpK")
        hd_loc = ""
        hd_job_category = ""
        for label in labels:
            text = label.get_text(strip=True)
            if "省" in text or "市" in text:
                hd_loc = text
            elif text in ["实习", "全职", "兼职"]:
                hd_job_category = text

        # 从 API 映射获取 link 和招聘类型
        post_info = job_name_to_id.get(announcement_name)
        if post_info:
            base_url = "https://gaush.zhiye.com/social/detail?jobAdId={}"
            link = base_url.format(post_info["postId"])
            hd_dept = "社会招聘" if post_info["postType"] == "campus" else "校园招聘"
        else:
            link = ''
            hd_dept = ""

        job_list.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": "",
            "hd_job_category": hd_job_category
        })

    # ===== 保存 JSON =====
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)

    return job_list
