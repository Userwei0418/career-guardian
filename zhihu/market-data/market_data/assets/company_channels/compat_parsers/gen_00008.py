
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for item in soup.find_all(class_='list-item-main'):
        announcement_name = item.find(class_='pos-name').get_text(strip=True)
        hd_dept = ""
        if item.find(class_='pos-department'):
            hd_dept = item.find(class_='pos-department').get_text(strip=True)
        hd_loc = item.find(class_='pos-locate').get_text(strip=True)
        hd_job_num = ""
        if item.find(class_='pos-num'):
            hd_job_num = item.find(class_='pos-num').get_text(strip=True)
        hd_job_category = ""
        if item.find(class_='pos-cate'):
            hd_job_category = item.find(class_='pos-cate').get_text(strip=True)
        publish_time = ""
        if  item.find('div', class_='pos-pubTime'):
            publish_time = item.find('div', class_='pos-pubTime').get_text(strip=True)
        job_entry = {
            "announcement_name": announcement_name,
            "publish_time": publish_time,  # Assuming publish_time is not available in the provided HTML
            "link": "",          # Assuming link is not available in the provided HTML
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        }

        job_list.append(job_entry)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)