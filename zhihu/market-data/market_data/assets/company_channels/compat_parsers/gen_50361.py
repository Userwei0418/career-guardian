
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    items = soup.find_all('div', class_='list-item-main')
    for item in items:
        announcement_name = item.find('div', class_='pos-name').get_text(strip=True)
        publish_time = item.find('div', class_='pos-pubTime').get_text(strip=True)
        link = item.find('div', class_='list-cell pos-name').find('span')['title']  # Assuming link is the title for now
        hd_dept = item.find('div', class_='pos-department').get_text(strip=True)
        hd_loc = item.find('div', class_='pos-locate').get_text(strip=True)
        hd_job_num = item.find('div', class_='pos-num').get_text(strip=True)
        hd_job_category = item.find('div', class_='pos-cate').get_text(strip=True)

        job_list.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": "",
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
