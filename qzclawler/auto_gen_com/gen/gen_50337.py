
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    table_rows = soup.find_all('tr', class_='el-table__row')
    
    data_list = []
    import requests

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
    }

    api_url = "https://www.zonst.com/api/zonst-recruitment-config/?jobs_name=&jobs_addr=&jobs_type=&recruitment_channel="

    job_name_to_id = {}
    page_index = 1

    # 使用 POST 请求
    response = requests.get(api_url, headers=headers, verify=False)
    print(response.url)
    if response.status_code == 200:
        res_json = response.json()
        res = res_json.get("data", [])
        print(res)
        for job in res:
            job_name = job.get("jobs_name", "")
            job_id = job.get("id", "")
            job_name_to_id[f"{job_name}"] = job_id
    print(job_name_to_id)
    print(len(job_name_to_id))
    for row in table_rows:
        cells = row.find_all('td')
        if len(cells) >= 6:
            announcement_name = cells[0].get_text(strip=True)
            hd_dept = cells[1].get_text(strip=True)
            hd_job_category = cells[2].get_text(strip=True)
            hd_job_num = cells[3].get_text(strip=True)
            hd_loc = cells[4].get_text(strip=True)
            link = ""  # Placeholder for the actual link, as it is not provided in the HTML
            if announcement_name == "游戏主美":
                continue
            if announcement_name in job_name_to_id:
                job_id = job_name_to_id[announcement_name]
                link = f"https://job.zonst.com/#/job-detail/{job_id}"
            else:
                link = ""
            data_list.append({
                "announcement_name": announcement_name,
                "publish_time": "",  # Placeholder for publish time, as it is not provided in the HTML
                "link": link,
                "hd_dept": "",
                "hd_loc": hd_loc,
                "hd_job_num": "",
                "hd_job_category": hd_job_category
            })
    
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(data_list, f, ensure_ascii=False, indent=4)
