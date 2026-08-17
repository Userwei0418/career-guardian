
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for item in soup.find_all('div', class_='right-list-item'):
        title = item.find('div', class_='item-left-title').text.strip()
        location_category = item.find('div', class_='item-left-class').text.strip().split(' | ')
        location = location_category[0]
        category = location_category[1] if len(location_category) > 1 else ''

        job_info = {
            "announcement_name": title,
            "publish_time": "",  # Assuming publish_time is not available in the provided HTML
            "link": "",  # Assuming link is not available in the provided HTML
            "hd_dept": "",  # Assuming hd_dept is not available in the provided HTML
            "hd_loc": location,
            "hd_job_num": "",  # Assuming hd_job_num is not available in the provided HTML
            "hd_job_category": category
        }

        job_list.append(job_info)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
