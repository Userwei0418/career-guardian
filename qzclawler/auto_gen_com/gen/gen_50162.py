
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for item in soup.find_all(class_='list-item-main'):
        announcement_name = item.find(class_='pos-name').get_text(strip=True)
        hd_dept = ""  # Placeholder as the HTML does not provide this information
        hd_loc = item.find(class_='pos-locate').get_text(strip=True)
        hd_job_category = item.find(class_='pos-cate').get_text(strip=True)
        publish_time = ""  # Placeholder as the HTML does not provide this information
        link = ""  # Placeholder as the HTML does not provide this information
        hd_job_num = ""  # Placeholder as the HTML does not provide this information

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
