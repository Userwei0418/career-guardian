
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    job_descriptions = soup.find_all('div', class_='job-des')

    for job in job_descriptions:
        title = job.find('div', class_='job-title').text.strip()
        details = job.find('div', class_='job-detail').text.strip().split(' | ')
        publish_time = job.find('span', class_='public-tm').text.strip().replace('截止日期 ', '')

        announcement_name = title
        hd_dept = details[0] if len(details) > 0 else ''
        hd_loc = details[2] if len(details) > 2 else ''
        hd_job_num = details[3] if len(details) > 1 else ''
        hd_job_category = ''  # Assuming this field is not available in the provided HTML

        job_info = {
            "announcement_name": announcement_name,
            "publish_time": "",
            "link": "",  # Assuming no link is provided in the HTML
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        }

        job_list.append(job_info)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
