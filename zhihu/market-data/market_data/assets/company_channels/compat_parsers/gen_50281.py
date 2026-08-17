
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for job in soup.find_all('div', class_='container-aOp138AX_X'):
        announcement_name = job.find('span', class_='title-u2qk9xX9Ie').text.strip()
        link = job.find('a')['href']
        # Assuming publish_time, hd_dept, hd_loc, hd_job_num, hd_job_category are not available in the provided HTML
        publish_time = ""
        hd_dept = ""
        hd_loc = ""
        hd_job_num = ""
        hd_job_category = ""

        job_info = {
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        }

        job_list.append(job_info)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
