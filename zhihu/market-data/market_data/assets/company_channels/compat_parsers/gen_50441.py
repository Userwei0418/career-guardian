
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for li in soup.find_all('li'):
        a_tag = li.find('a')
        job_one = a_tag.find('div', class_='job-one')

        announcement_name = job_one.h1.text.strip()
        publish_time = job_one.find('p').text.strip()
        link = a_tag['href']

        job_details = job_one.find('div', class_='job-d').find_all('span')
        hd_dept = job_details[0].text.strip() if len(job_details) > 0 else ''
        hd_loc = job_details[1].text.strip() if len(job_details) > 1 else ''
        hd_job_num = job_details[2].text.strip() if len(job_details) > 2 else ''
        hd_job_category = ''  # Assuming this field is not available in the provided HTML

        job_list.append({
            "announcement_name": announcement_name,
            "publish_time": "",
            "link": link,
            "hd_dept": "",
            "hd_loc": "",
            "hd_job_num": "",
            "hd_job_category": ""
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
