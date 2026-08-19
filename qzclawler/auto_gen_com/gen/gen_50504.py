
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    table_rows = soup.select('div.apply_list table tr')[1:]  # Skip header row
    job_list = []

    for row in table_rows:
        cols = row.find_all('td')
        if len(cols) < 9:
            continue  # Skip rows that do not have enough columns

        announcement_name = cols[1].get_text(strip=True)  # 职位名称
        publish_time = cols[7].get_text(strip=True)  # 发布时间
        link = cols[9].find('a')['href'] if cols[9].find('a') else ""  # 链接
        hd_dept = cols[5].get_text(strip=True)  # 招聘单位
        hd_loc = cols[6].get_text(strip=True)  # 工作地点
        hd_job_num = cols[4].get_text(strip=True) if len(cols) > 4 else ""  # 招聘人数
        hd_job_category = cols[2].get_text(strip=True)  # 学历要求

        job_list.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
