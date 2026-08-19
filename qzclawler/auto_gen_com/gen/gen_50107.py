import json
from bs4 import BeautifulSoup


def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    positions = []
    import requests
    import time
    import json

    url = "https://career.cmbchina.com/api/campusRecruitmentWebsite/job/getList"

    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
        "Cookie": "$initData={%22startTime%22:1756797782404%2C%22hasToJobDetailSchool%22:false%2C%22hasToJobDetailSocial%22:true}; processID1=17567997220909319.234261250185; processID2=17567997272831600.760712682796"
    }

    job_map = {}  # jobDisplay -> location 映射
    page_size = 50
    recruit = {
        "school": "96574F8D-C7ED-4772-AE7C-BAC896D190C1",
        "intrn": "DF94FD6D-26D3-4A19-9E69-577C4BA1DE82"
    }

    for recruit_type, recruit_type_id in recruit.items():
        page = 1  # 每种招聘类型从第一页开始
        while True:
            payload = {
                "orgIdList": [],
                "keywords": "",
                "locationIdList": [],
                "pageIndex": page,
                "pageSize": page_size,
                "jobTypeIdList": [],
                "recruitmentTypeId": recruit_type_id
            }
            print(f"请求第 {page} 页，类型：{recruit_type}")
            resp = requests.post(url, json=payload, headers=headers)

            if resp.status_code != 200:
                print(f"请求失败: {resp.status_code}")
                break

            data = resp.json()
            # 先调试看下返回结构
            if page == 1:
                print(json.dumps(data, indent=2, ensure_ascii=False))

            records = data.get("body", {}).get("data", [])
            if not records:
                print("没有更多数据，抓取结束。")
                break

            for job in records:
                job_name = job.get("jobDisplay")
                # 这里先用 publishGID 测试，后续确认字段换成 cityName/workLocation
                job_loc = job.get("publishGID")
                print(job_name, "-", job_loc)
                if job_name:
                    job_map[job_name] = job_loc

            page += 1
            time.sleep(1)

    print("最终结果：", job_map)

    for item in soup.find_all('div', class_='position-item'):
        title = item.find('div', class_='title').text.strip()
        details = item.find('div', class_='deatil').find_all('span')

        if len(details) >= 3:
            hd_dept = details[0].text.strip()
            hd_loc = details[2].text.strip()
            hd_job_category =details[1].text.strip()
        else:
            hd_dept = hd_loc = hd_job_category = ""
        link = ""
        for k ,v in job_map.items():
            if k == title:
                job_id = v
                link = f"https://career.cmbchina.com/positionDetail/school?publishId={job_id}"
                break

        position = {
            "announcement_name": title,
            "publish_time":"2025-08-18",
            "link": link,  # Assuming no link is provided in the HTML
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": "",  # Assuming no job number is provided in the HTML
            "hd_job_category": hd_job_category
        }

        positions.append(position)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(positions, f, ensure_ascii=False, indent=4)


