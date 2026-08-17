
import json
import re

from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for job in soup.find_all('div', class_='job_nr'):
        announcement_name = job.h3.text.split(' ')[0]
        publish_time = ""  # Assuming publish_time is not available in the provided HTML
        link = ""
        hd_dept = ""  # Assuming hd_dept is not available in the provided HTML
        hd_loc = job.find('span').text
        hd_job_num = ""  # Assuming hd_job_num is not available in the provided HTML
        hd_job_category = job.h3.text.split(' ')[1] if len(job.h3.text.split(' ')) > 1 else ""

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
