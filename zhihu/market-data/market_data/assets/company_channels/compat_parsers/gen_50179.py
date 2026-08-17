
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for job in soup.find_all('div', class_='container-aOp138AX_X'):
        announcement_name = job.find('span', class_='title-u2qk9xX9Ie').text.strip()
        publish_time = job.find('span', class_='published-at-PQ5IBWmbJV').text.replace('发布于 ', '').strip()
        link = job.find('a')['href']
        hd_dept = job.find('div', class_='sd-Ellipsis-hiddenContent-1Skwh').text.strip()
        hd_loc = '北京'  # Placeholder as location is not provided in the HTML
        hd_job_num = ''  # Placeholder as job number is not provided in the HTML
        hd_job_category = ''  # Placeholder as job category is not provided in the HTML

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
