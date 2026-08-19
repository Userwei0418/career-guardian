import json
from bs4 import BeautifulSoup


def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    positions = []
    import uuid
    import requests

    url = "https://careers.midea.com/backend/school/position/common/position/list"
    track_id = str(uuid.uuid4())
    full_url = f"{url}?_ihr_log_trackId={track_id}"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
        "Content-Type": "application/json",
        "Cookie": "language=zh-CN; timeZone=8; path=/"
    }

    job_name_to_ids = {}
    page_index = 1  # 从第1页开始

    while True:
        payload = {
            "keyword": "",
            "superiorIds": [],
            "recruitCategoryIds": [],
            "workPlaceCodes": [],
            "projectRuleId": "65887882-8def-4b50-b0fa-39c5280a2cab",
            "pageIndex": page_index,
            "pageSize": 10
        }

        res = requests.post(full_url, json=payload, headers=headers)
        result = res.json()

        print(f"Page {page_index}: {result}")

        # 检查响应是否成功
        if result.get("code") != "0":
            print(f"Error: Response code is {result.get('code')}")
            break

        data_section = result.get("data", {})
        jobs = data_section.get("data", [])
        total = data_section.get("total", 0)
        info = data_section.get("info", {})
        total_page = info.get("totalPage", 0)

        # 处理职位数据
        for job in jobs:
            job_name_to_ids[job['projectPositionName']] = {"positionId":job["positionId"],"projectRuleId":job["projectRuleId"],"recruitCategoryId":job["recruitCategoryId"]}

        # 如果没有更多数据，退出循环
        if not jobs:
            print(f"No more jobs found on page {page_index}")
            break

        # 检查是否已经到最后一页
        if page_index >= total_page:
            break

        page_index += 1

    print(job_name_to_ids)
    print(f"Total jobs collected: {len(job_name_to_ids)}")

    for item in soup.find_all('div', class_='position-item'):
        title = item.find('span', class_='card-name').text.strip()
        tags = item.find_all('span')
        category = tags[0].text.strip() if len(tags) > 0 else ''
        job_type = tags[1].text.strip() if len(tags) > 1 else ''
        location = tags[2].text.strip() if len(tags) > 2 else ''
        if title in job_name_to_ids:
            positionId = job_name_to_ids[title]["positionId"]
            projectRuleId = job_name_to_ids[title]["projectRuleId"]
            recruitCategoryId = job_name_to_ids[title]["recruitCategoryId"]
            link = f"https://careers.midea.com/recruit-school-out/post/details?projectRuleId={projectRuleId}&positionId={positionId}&recruitCategoryId={recruitCategoryId}&projectType=1"
        else:
            link = ""
        position_data = {
            "announcement_name": title,
            "publish_time": "",  # Placeholder as no publish time is provided in the HTML
            "link": link,  # Placeholder as no link is provided in the HTML
            "hd_dept": category,
            "hd_loc": location,
            "hd_job_num": job_type,
            "hd_job_category": category
        }

        positions.append(position_data)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(positions, f, ensure_ascii=False, indent=4)
