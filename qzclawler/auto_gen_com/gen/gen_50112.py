import json
import requests
import time
from bs4 import BeautifulSoup
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    # ===== 新 API 地址 =====
    api_url = "https://sany.zhiye.com/api/Jobad/GetJobAdPageList"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
        "Content-Type": "application/json",
        "Referer": "https://sany.zhiye.com/"
    }

    # ===== 招聘类型映射 =====
    types = {
        "campus": {"val": 1, "dept": "校园招聘", "base_url": "https://sany.zhiye.com/campus/detail?jobAdId={}"},
        "social": {"val": 2, "dept": "社会招聘", "base_url": "https://sany.zhiye.com/social/detail?jobAdId={}"},
        "intern": {"val": 3, "dept": "实习招聘", "base_url": "https://sany.zhiye.com/intern/detail?jobAdId={}"}
    }

    # ===== 拉取全量职位数据，构造 映射表 =====
    postid_map = {}
    for t_name, t_info in types.items():
        page_index = 0
        while True:
            payload = {
                "PageIndex": page_index,
                "PageSize": 100,
                "Category": t_info["val"],
                "KeyWords": "",
                "SpecialType": 0,
                "PortalId": "",
                "recruitType": "",
                "DisplayFields": ["Category", "Kind", "LocId", "Salary", "Degree",
                                  "YearsOfWorking", "ClassificationOne", "ClassificationTwo"]
            }
            try:
                resp = requests.post(api_url, json=payload, headers=headers, verify=False)
                resp.raise_for_status()
                jobs = resp.json().get("Data", [])
            except Exception as e:
                print(f"[{t_name}] 拉取失败: {e}")
                break

            if not jobs:
                break

            for job in jobs:
                postid_map[job["JobAdName"].strip()] = {
                    "postId": job["Id"],
                    "dept": t_info["dept"],
                    "base_url": t_info["base_url"]
                }

            if len(jobs) < payload["PageSize"]:
                break

            page_index += 1
            time.sleep(0.2)

    print(f"职位名称 -> postId 映射完成，共 {len(postid_map)} 条")

    # ===== 解析 HTML 并合并接口数据 =====
    for item in soup.find_all("div", class_="style__STListItem-editor__sc-10r1nhd-0"):
        announcement_name = item.find("div", class_="style__STJobTitle-editor__sc-10r1nhd-4").get_text(strip=True)
        publish_time = item.find("div", class_="style__STJobTime-editor__sc-10r1nhd-16").get_text(strip=True).replace(" 发布", "")

        # ===== 标签提取 =====
        labels = item.find_all("div", class_="style__STLabelText-editor__sc-10r1nhd-13 cJYhpK")
        hd_loc, hd_job_category = "", ""
        for label in labels:
            text = label.get_text(strip=True)
            if "省" in text or "市" in text:
                hd_loc = text
            elif text in ["实习", "全职", "兼职"]:
                hd_job_category = text

        # ===== 匹配接口数据 =====
        post_info = postid_map.get(announcement_name)
        if post_info:
            link = post_info["base_url"].format(post_info["postId"])
            hd_dept = post_info["dept"]
        else:
            link, hd_dept = "", ""

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

    print(f"已生成 JSON 文件: {tempfile}")
