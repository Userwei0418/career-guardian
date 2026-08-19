
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for job in soup.find_all('div', class_='recruitment-content-list'):
        announcement_name = job.find('span', class_='job').get_text(strip=True) if job.find('span', class_='job') else ""
        publish_time = job.find('span', class_='time').get_text(strip=True).replace('发布', '') if job.find('span', class_='time') else ""
        link = ""  # Assuming no link is provided in the HTML
        hd_dept = job.find('span', class_='department').get_text(strip=True) if job.find('span', class_='department') else ""
        hd_loc = job.find('span', class_='place').get_text(strip=True).replace("[", "").replace("]", "").replace("【", "").replace("】", "") if job.find('span', class_='place') else ""
        hd_job_num = ""  # Assuming no job number is provided in the HTML
        hd_job_category = ""  # Assuming no job category is provided in the HTML

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
