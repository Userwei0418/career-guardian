
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for job in soup.select('.job-list li'):
        company_name = job.select_one('div:nth-of-type(1)').text.strip()
        job_title = job.select_one('div:nth-of-type(2)').text.strip()
        job_location = job.select_one('div:nth-of-type(3)').text.strip()
        job_link = job.select_one('a.apply')['href']

        job_info = {
            "announcement_name": job_title,
            "publish_time": "",  # Assuming no publish time is provided in the HTML
            "link": job_link,
            "hd_dept": company_name,
            "hd_loc": job_location,
            "hd_job_num": "",  # Assuming no job number is provided in the HTML
            "hd_job_category": ""  # Assuming no job category is provided in the HTML
        }

        job_list.append(job_info)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
