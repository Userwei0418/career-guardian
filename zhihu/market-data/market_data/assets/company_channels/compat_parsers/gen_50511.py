
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for box in soup.find_all('div', class_='box cp'):
        announcement_name = box.find('span', class_='posts-name').get_text(strip=True) if box.find('span', class_='posts-name') else ""
        publish_time = ""  # Assuming publish_time is not available in the provided HTML
        link = ""  # Assuming link is not available in the provided HTML
        hd_dept = ""  # Assuming hd_dept is not available in the provided HTML
        hd_loc = box.find('p', class_='base').get_text(strip=True).split('|')[0] if box.find('p', class_='base') else ""
        hd_job_num = box.find(text="招聘人数：").split('：')[-1].strip() if box.find(text="招聘人数：") else ""
        hd_job_category = box.find('p', class_='base').get_text(strip=True).split('|')[1] if box.find('p', class_='base') else ""

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
