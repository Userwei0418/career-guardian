import json
from bs4 import BeautifulSoup


def extract_table_from_html(htmlcontext, tempfile):
    import base64
    import json

    import requests
    appi_url = "https://www.hotjob.cn/wt/qianxin/web/mode400/position/list"

    headers = {
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36 Edg/117.0.2045.60",
        "Referer": "https://www.hotjob.cn/wt/qianxin/web/index",

    }
    job_name_to_id = {}
    jobs = []
    page_index = 1
    while True:
        payload = {
            "rowSize": 20,
            "recruitType": 2,
            "rowIndex": page_index

        }

        res = requests.post(appi_url, data=payload, headers=headers)
        totle = res.json().get("data", {}).get("rowCount", 0)
        jobs = res.json().get("data", {}).get("details", [])

        for job in jobs:
            job_name_to_id[job["PostName"]] = {
                "PostId": job["PostId"],
                "RecruitType": job["RecruitType"],
                "RecruitTypeName": job["RecruitTypeName"]
            }
        page_index += 1
        if page_index > (totle // 20) + 1:
            print("done")
            break
    print(job_name_to_id)

    soup = BeautifulSoup(htmlcontext, 'html.parser')
    rows = soup.find_all('tr', attrs={'ng-repeat': 'info in workInfo.details'})

    data_list = []

    for row in rows:
        cells = row.find_all('td')
        if len(cells) >= 8:
            announcement_name = cells[0].get_text(strip=True)
            hd_loc =""
            hd_dept = ""
            hd_job_category = ""
            hd_job_num = ""
            publish_time = ""

            if announcement_name in job_name_to_id:
                name =  announcement_name
                json_str = json.dumps(job_name_to_id[name], ensure_ascii=False, separators=(',', ':'))
                encoded = base64.b64encode(json_str.encode("utf-8")).decode("utf-8")
                link = f"https://www.hotjob.cn/wt/qianxin/web/index#!/pd/{encoded}"
            else :
                link = ""

            data_list.append({
                "announcement_name": announcement_name,
                "publish_time": publish_time,
                "link": link,
                "hd_dept": hd_dept,
                "hd_loc": hd_loc,
                "hd_job_num": hd_job_num,
                "hd_job_category": hd_job_category
            })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(data_list, f, ensure_ascii=False, indent=4)

