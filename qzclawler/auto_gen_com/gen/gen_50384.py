
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for li in soup.find_all('li'):
        announcement_name = li.find('a', class_='articleid').get('title')
        publish_time = li.find('span', class_='wp-new-ar-pro-time').text
        link = li.find('a', class_='articleid').get('href')
        hd_dept = ""  # Placeholder as the HTML does not provide this information
        hd_loc = ""   # Placeholder as the HTML does not provide this information
        hd_job_num = ""  # Placeholder as the HTML does not provide this information
        hd_job_category = ""  # Placeholder as the HTML does not provide this information

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
