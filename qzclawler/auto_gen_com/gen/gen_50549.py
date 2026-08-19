
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for job in soup.find_all('ul', class_='list clearfix'):
        announcement_name = job.find('li', class_='list1').get_text(strip=True) if job.find('li', class_='list1') else ""
        publish_time = ""  # No publish time in the provided HTML
        link = job.find('li', class_='list1').find('a')['href'] if job.find('li', class_='list1') and job.find('li', class_='list1').find('a') else ""
        hd_dept = job.find('li', class_='list3').get_text(strip=True) if job.find('li', class_='list3') else ""
        hd_loc = job.find('li', class_='list4').get_text(strip=True) if job.find('li', class_='list4') else ""
        hd_job_num = ""  # No job number in the provided HTML
        hd_job_category = job.find('li', class_='list2').get_text(strip=True) if job.find('li', class_='list2') else ""

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
