import requests
import time
import urllib3
import json
from bs4 import BeautifulSoup

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def extract_table_from_html(htmlcontext, tempfile):

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
        link = ""

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
