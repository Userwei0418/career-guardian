import json
from bs4 import BeautifulSoup
import requests
import time

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_items = soup.find_all('div', class_='job__item')

    # 请求的 URL
    url = "https://careers.oppo.com/openapi/position/pageNew"
    # 请求头
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
        "tenant-id": "1000",
        "authorization": "",  # 如果需要授权可以填这里
    }

    page_index = 1
    all_job_name_to_id = {}

    # 翻页获取所有职位 ID
    while True:
        payload = {
            "pageNum": page_index,
            "pageSize": 50,
            "positionName": "",
            "projectList": [
                {
                    "projectId": 25,
                    "recruitmentType": "Graduate",
                    "isAllNode": "Y",
                    "themeList": ["AI Theme"]
                }
            ],
            "positionTypeList": [],
            "workCityCodeList": [],
            "shareId": ""
        }

        response = requests.post(url, headers=headers, data=json.dumps(payload))
        data = response.json().get("data", {})
        jobs = data.get("records", [])

        if not jobs:
            break  # 没有更多职位，退出循环

        # 汇总职位名称 -> ID
        for job in jobs:
            all_job_name_to_id[job["positionName"]] = job["idRecruitPosition"]

        print(f"第 {page_index} 页抓取完成，共抓取 {len(jobs)} 条职位")
        page_index += 1
        time.sleep(0.5)

    # 解析 HTML 并结合 API 的职位 ID
    job_list = []
    for job in job_items:
        title = job.find('span', class_='job_code').text.strip()
        publish_time = job.find('span', class_='pub_date').text.strip()
        job_id = all_job_name_to_id.get(title)
        link = f'https://careers.oppo.com/university/oppo/campus/post/{job_id}' if job_id else ''

        hd_dept = ''  # HTML中未提供
        hd_loc = job.find('span', class_='city_name').text.strip()
        hd_job_num = ''  # HTML中未提供
        hd_job_category = job.find_all('div', class_='el-space__item')[1].text.strip()  # 假设是第二个元素

        job_list.append({
            "announcement_name": title,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        })

    # 写入文件
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)

    print(f"共解析 {len(job_list)} 条职位信息，已写入 {tempfile}")
