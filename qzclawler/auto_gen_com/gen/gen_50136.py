
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

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
        "Referer": "https://careers.aliyun.com/campus/position-list?",

    }
    type = {
        "school": {"batchid": "", "categoryType": "freshman"},
        "intern": {"batchid": "170", "categoryType": "talentPlan"}
    }
    job_name_to_id = {}
    for key, value in type.items():
        page_index = 1
        while True:
            payloda = {

                "channel": "campus_group_official_site",
                "language": "zh",
                "pageSize": 100,
                "batchId": value["batchid"],
                "subCategories": "",
                "regions": "",
                "customDeptCode": "",
                "corpCode": "",
                "pageIndex": page_index,
                "key": "",
                "categoryType": value["categoryType"]

            }
            res = session.post(url, json=payloda, headers=headers)
            jobs = res.json().get("content", []).get("datas", [])
            for job in jobs:
                job_name_to_id[job["name"]] = job["id"]

            page_index += 1
            if not jobs or page_index > 5:
                break


    job_elements = soup.find_all('div', class_='jwPAC7jgWIKUro5l4bE3')
    
    for job in job_elements:
        announcement_name = job.find('span').text
        publish_time = job.find('div', class_='oAdZgV3YZC3NawYz0Ocyy').text.replace('更新于 ', '')
        hd_job_category = job.find('div', class_='_3JJTjjGoQPkS4t1NWmlpAM').text
        hd_loc = job.find('div', class_='O2l16_NlF-uGFa5WEZRHY').text
        if announcement_name in job_name_to_id:
            link = f"https://careers.aliyun.com/campus/position-detail?lang=zh&positionId={job_name_to_id[announcement_name]}"
        else:
            link = ''
        hd_dept = ''  # Assuming department is not provided in the HTML
        hd_job_num = ''  # Assuming job number is not provided in the HTML

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
