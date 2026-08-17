
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for item in soup.find_all('div', class_='list-item-main'):
        announcement_name = item.find('div', class_='pos-name').get_text(strip=True) if item.find('div', class_='pos-name') else ""
        publish_time = item.find('div', class_='pos-pubTime').get_text(strip=True) if item.find('div', class_='pos-pubTime') else ""
        link = ""  # Assuming no link is provided in the HTML
        hd_dept = ""  # Assuming no department is provided in the HTML
        hd_loc = item.find('div', class_='pos-locate').get_text(strip=True) if item.find('div', class_='pos-locate') else ""
        hd_job_num = item.find('div', class_='pos-num').get_text(strip=True) if item.find('div', class_='pos-num') else ""
        hd_job_category = item.find('div', class_='pos-cate').get_text(strip=True) if item.find('div', class_='pos-cate') else ""

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
