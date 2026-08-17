
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for li in soup.select('ul > li'):
        announcement_name = li.select_one('.pp1').get_text(strip=True) if li.select_one('.pp1') else ""
        hd_dept = li.select_one('.pp2').get_text(strip=True) if li.select_one('.pp2') else ""
        hd_loc = li.select_one('.pp3').get_text(strip=True) if li.select_one('.pp3') else ""
        hd_job_num = li.select_one('.pp4').get_text(strip=True) if li.select_one('.pp4') else ""
        link = li.select_one('.pp5 a')['href'] if li.select_one('.pp5 a') else ""

        job_entry = {
            "announcement_name": announcement_name,
            "publish_time": "",  # Assuming publish_time is not available in the provided HTML
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": ""  # Assuming hd_job_category is not available in the provided HTML
        }

        job_list.append(job_entry)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
