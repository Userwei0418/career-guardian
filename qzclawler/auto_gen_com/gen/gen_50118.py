import json
import time
import requests
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    apiurl = "https://hr.vivo.com/api/social/webSite/portal/page"
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }

    jobs = []
    page_index = 1
    total_num = 0

    # 分页获取 API 数据
    while True:
        data = {
            "city_code_list": [],
            "company_id": 1,
            "group_id": 1,
            "user_id": None,
            "job_category_id_list": [],
            "keyword": "",
            "loading": True,
            "max_results": 25,
            "page": page_index,
            "yoe_list": []
        }
        try:
            res = requests.post(apiurl, json=data, headers=headers, timeout=5)
            if res.status_code != 200:
                print(f"Request failed with status {res.status_code}, stopping...")
                break
            response_data = res.json()
        except Exception as e:
            print(f"Request error: {e}, stopping...")
            break

        jobs_data = response_data.get("data", [])
        meta = response_data.get("meta", {})
        total_num = meta.get("total", 0) if isinstance(meta, dict) else 0

        for job in jobs_data:
            job_id = job.get("job_id", "")
            job_code = job.get("job_code", "")
            job_title = job.get("job_title", "")
            full_job_title = f"{job_title}（{job_code}）" if job_code else job_title
            job['full_job_title'] = full_job_title
            jobs.append(job)

        if not jobs_data or page_index > (total_num // 25 + 1):
            break

        page_index += 1
        time.sleep(0.2)

    # 构造职位名称到 ID 的映射
    job_name_to_id = {job["full_job_title"]: job.get("job_id", "") for job in jobs}

    # 解析 HTML 页面
    job_cards = soup.find_all(
        'div',
        class_='w-full 2xl:rounded-3xl lg:rounded-[0.875rem] rounded-xl p-4 lg:p-5 bg-white cursor-pointer hover:shadow-lg mb-4'
    )

    for job in job_cards:
        try:
            announcement_name = job.find('div', class_='flex sm:items-center relative').text.strip().replace("急招","")
        except AttributeError:
            announcement_name = ""
        hd_dept = ""
        hd_loc =  ""
        hd_job_num = ""
        hd_job_category = ""

        job_id = job_name_to_id.get(announcement_name, "")
        link = f"https://hr.vivo.com/job-detail?_irjid={job_id}" if job_id else ""

        job_info = {
            "announcement_name": announcement_name,
            "publish_time": "",  # HTML 中没有提供时用空
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        }

        job_list.append(job_info)

    # 写入 JSON 文件
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)

    print(f"Total jobs extracted: {len(job_list)}")
