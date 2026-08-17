
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    rows = soup.select('table tbody tr')
    for i in range(0, len(rows), 2):
        job_name = rows[i].find('h2').get_text(strip=True) if rows[i].find('h2') else ""
        link = rows[i].find('a')['href'] if rows[i].find('a') else ""
        publish_time = rows[i + 1].find_all('a')[-1].get_text(strip=True).replace(" 发布", "") if rows[i + 1].find_all('a') else ""

        job_info = {
            "announcement_name": job_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": "",
            "hd_loc": "",
            "hd_job_num": "",
            "hd_job_category": ""
        }

        job_list.append(job_info)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
