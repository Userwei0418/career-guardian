
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    import requests

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
    }

    api_url = "https://mdpi.cn/api/jobs?"

    job_name_to_id = {}
    page_index = 1

    while True:
        params = {
            "office_id": "",
            "department_id": "",
            "page": page_index,
            "job_name": ""
        }

        # 使用 POST 请求
        response = requests.get(api_url, headers=headers, data=params, verify=False)

        if response.status_code == 200:
            res_json = response.json()
            res = res_json.get("data", [])
            jobs = res_json.get("data", []).get("list", [])
            for job in jobs:
                job_name = job.get("name", "")
                job_id = job.get("id", "")
                job_name_to_id[job_name] = job_id
            total = res.get("total_count", 0)
            if page_index * 16 > total:
                break
            page_index += 1
        print(job_name_to_id)
    table_rows = soup.select('table tbody tr')
    
    data_list = []
    
    for row in table_rows:
        cols = row.find_all('td')
        if len(cols) >= 4:
            announcement_name = cols[0].get_text(strip=True)
            hd_dept = cols[1].get_text(strip=True)
            hd_loc = cols[2].get_text(strip=True)
            hd_job_num = ""  # Placeholder as job number is not provided in the HTML
            hd_job_category = ""  # Placeholder as job category is not provided in the HTML
            publish_time = ""  # Placeholder as publish time is not provided in the HTML
            link = ""  # Placeholder as link is not provided in the HTML
            if announcement_name in job_name_to_id:
                job_id = job_name_to_id[announcement_name]
                link = f"https://mdpi.cn/career/recruit/jobs?id={job_id}&fromPath=social-recruit"
            else:
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
