
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for item in soup.find_all(class_='list-item-main'):
        announcement_name = item.find(class_='pos-name').get_text(strip=True)
        hd_loc = item.find(class_='pos-locate').get_text(strip=True)
        hd_job_num = item.find(class_='pos-num').get_text(strip=True)
        hd_dept = item.find(class_='pos-company').get_text(strip=True)
        # Assuming other fields are not available in the provided HTML
        job_entry = {
            "announcement_name": announcement_name,
            "publish_time": "",  # Placeholder as it's not provided in the HTML
            "link": "",          # Placeholder as it's not provided in the HTML
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": ""  # Placeholder as it's not provided in the HTML
        }
        job_list.append(job_entry)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)