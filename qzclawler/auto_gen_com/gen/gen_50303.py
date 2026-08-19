import json
from bs4 import BeautifulSoup


def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    rows = soup.select('table.el-table__body tr.el-table__row')

    data_list = []
    import requests

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
    }

    api_url = "https://job.dahuatech.com/talent-pool/api/bs-info/list-position-by-search"

    job_name_to_id = {}
    page_index = 1

    params = {
  "companyCategory": "",
  "positionCategory": "",
  "workPlaceCode": "",
  "recruitType": 2
}

    # 使用 POST 请求
    response = requests.post(api_url, headers=headers, json=params)

    if response.status_code == 200:
        res_json = response.json()
        jobs = res_json.get("data", [])

        for job in jobs:
            job_name = job.get("jobAdName", "")
            job_id = job.get("jobAdId", None)
            job_name_to_id[job_name] = job_id

        print(job_name_to_id)
    else:
        print(f"请求失败，状态码: {response.status_code}")
    for row in rows:
        cols = row.find_all('td')

        # 安全提取，每个字段都用 try/except 或条件判断
        announcement_name = cols[0].get_text(strip=True) if len(cols) > 0 else ""
        hd_dept = cols[1].get_text(strip=True) if len(cols) > 1 else ""
        hd_job_category = cols[2].get_text(strip=True) if len(cols) > 2 else ""
        hd_loc = cols[3].get_text(strip=True) if len(cols) > 3 else ""
        publish_time = cols[4].get_text(strip=True) if len(cols) > 4 else ""

        # 链接提取（假如有 a 标签）
        link_tag = cols[0].find('a') if len(cols) > 0 else ""
        link = link_tag['href'] if link_tag and link_tag.has_attr('href') else ""
        for job in job_name_to_id:
            if job == announcement_name:
                link = f"https://job.dahuatech.com/#/CampusApply?id={job_name_to_id[job]}"
        # 职位数量占位
        hd_job_num = ""

        data_list.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        })

    # 写入 JSON 文件
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(data_list, f, ensure_ascii=False, indent=4)
