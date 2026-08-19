
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for item in soup.find_all('div', class_='list-item-main'):
        announcement_name = item.find('div', class_='pos-name').get_text(strip=True)
        publish_time = ""  # Assuming publish_time is not available in the provided HTML
        link = ""  # Assuming link is not available in the provided HTML
        hd_dept = ""  # Assuming hd_dept is not available in the provided HTML
        hd_loc = item.find('div', class_='pos-locate').get_text(strip=True)
        hd_job_num = ""  # Assuming hd_job_num is not available in the provided HTML
        hd_job_category = item.find('div', class_='pos-cate').get_text(strip=True)

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
