
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for item in soup.find_all(class_='p_loopitem'):
        announcement_name = item.find(class_='e_text-28').get_text(strip=True) if item.find(class_='e_text-28') else ""
        publish_time = item.find(class_='e_timeFormat-13').get_text(strip=True) if item.find(class_='e_timeFormat-13') else ""
        link = item.find('a')['href'] if item.find('a') else ""
        hd_dept = ""  # Assuming this field is not present in the provided HTML
        hd_loc = item.find(class_='e_text-24').get_text(strip=True) if item.find(class_='e_text-24') else ""
        hd_job_num = item.find(class_='e_text-16').get_text(strip=True) if item.find(class_='e_text-16') else ""
        hd_job_category = ""  # Assuming this field is not present in the provided HTML

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
