
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for li in soup.select('.list ul li'):
        announcement_name = li.a.get_text(strip=True)
        publish_time = li.a.find('div', class_='date2').get_text(strip=True)
        link = li.a['href']

        # Placeholder values for the other fields as they are not present in the provided HTML
        hd_dept = ""
        hd_loc = ""
        hd_job_num = ""
        hd_job_category = ""

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
