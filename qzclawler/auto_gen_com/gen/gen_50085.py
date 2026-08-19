import json
import requests
import time
import urllib3
from bs4 import BeautifulSoup

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def extract_table_from_html(htmlcontext, tempfile):
    """
    先调用 API 获取职位映射表（职位名 -> (ID, 来源)），
    然后解析 HTML 构造职位列表，用职位名字匹配生成不同来源的 link。
    """
    # ================= API 获取职位映射表 =================
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
        "Content-Type": "application/json",
        "Referer": "https://gdhw.zhiye.com/"
    }

    apis = [
        {
            "url": "https://neusoft-campus.zhiye.com/api/Jobad/GetJobAdPageList",
            "types": {"campus": 1, "social": 2, "intern": 3},
            "source": "campus"
        },
        {
            "url": "https://neusoft-career.zhiye.com/api/Jobad/GetJobAdPageList",
            "types": {"campus": 1, "social": 2},
            "source": "social"
        }
    ]

    job_name_to_info = {}  # 职位名 -> (ID, 来源)
    for api in apis:
        url = api["url"]
        source = api["source"]
        types = api["types"]
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
                                      "YearsOfWorking", "ClassificationOne", "ClassificationTwo"]
                }
                try:
                    resp = requests.post(url, json=payload, headers=headers, verify=False, timeout=10)
                    jobs = resp.json().get("Data", [])
                except Exception as e:
                    print(f"  请求失败: {e}")
                    break

                if not jobs:
                    break

                for job in jobs:
                    name = job.get("JobAdName")
                    job_id = job.get("Id")
                    if name and job_id:
                        job_name_to_info[name] = (job_id, source)

                page_index += 1
                time.sleep(0.3)

    print(f"映射表大小: {len(job_name_to_info)}")

    # ================= HTML 解析 =================
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for item in soup.find_all('div', class_='style__STListItem-editor__sc-10r1nhd-0'):
        announcement_name_tag = item.find('div', class_='style__STJobTitle-editor__sc-10r1nhd-4')
        announcement_name = announcement_name_tag.get_text(strip=True) if announcement_name_tag else ""
        publish_tag = item.find('div', class_='style__STJobTime-editor__sc-10r1nhd-16')
        publish_time = publish_tag.get_text(strip=True).replace(' 发布', '') if publish_tag else ""

        # ================= 标签解析 =================
        labels = item.select("div.style__STLabelText-editor__sc-10r1nhd-13.cJYhpK")
        hd_loc = ""
        hd_job_num = ""
        hd_job_category = ""

        for label in labels:
            text = label.get_text(strip=True)
            if "·" in text:  # 地点
                hd_loc = text
            elif text.startswith("在招"):  # 招聘人数
                hd_job_num = text
            else:  # 岗位类别
                hd_job_category = text

        # 根据职位名匹配生成 link
        info = job_name_to_info.get(announcement_name)
        if info:
            job_id, source = info
            if source == "campus":
                link = f"https://neusoft-campus.zhiye.com/campus/detail?jobAdId={job_id}"
            else:  # social
                link = f"https://neusoft-career.zhiye.com/social/detail?jobAdId={job_id}"
        else:
            link = ""

        job_list.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category,
            "hd_dept": "",  # HTML中没有提供
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)

    print(f"解析 HTML 完成，职位总数: {len(job_list)}")


