
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for job in soup.find_all('div', class_='container-aOp138AX_X'):
        announcement_name =  job.find('span', class_='title-u2qk9xX9Ie').text.strip() if job.find('span', class_='title-u2qk9xX9Ie') else ""
        link = job.find('a')['href']
        hd_dept = ""
        hd_job_category =  ""
        hd_loc =  ""
        hd_job_num = ""  # Placeholder as the job number is not provided in the HTML
        publish_time = ""  # Placeholder as the publish time is not provided in the HTML

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
