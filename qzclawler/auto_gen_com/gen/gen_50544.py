
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for item in soup.find_all('div', class_='list-item-main'):
        announcement_name = item.find('div', class_='pos-name').get_text(strip=True) if item.find('div', class_='pos-name') else ""
        hd_job_num = item.find('div', class_='pos-num').get_text(strip=True) if item.find('div', class_='pos-num') else ""
        hd_loc = item.find('div', class_='pos-locate').get_text(strip=True) if item.find('div', class_='pos-locate') else ""
        hd_dept = item.find('div', class_='pos-department').get_text(strip=True) if item.find('div', class_='pos-department') else ""
        hd_job_category = item.find('div', class_='pos-workType').get_text(strip=True) if item.find('div', class_='pos-workType') else ""
        
        job_list.append({
            "announcement_name": announcement_name,
            "publish_time": "",  # Assuming publish_time is not available in the provided HTML
            "link": "",          # Assuming link is not available in the provided HTML
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
