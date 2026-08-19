
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    job_items = soup.find_all('a', class_='job-item')
    
    for job in job_items:
        announcement_name = job.find('span', class_='jname').get_text(strip=True) if job.find('span', class_='jname') else ""
        publish_time = job['sensorsdata'].split('"jobTime":"')[1].split('"')[0] if 'sensorsdata' in job.attrs else ""
        link = job['href'] if 'href' in job.attrs else ""
        hd_dept = ""  # No department info available in the provided HTML
        hd_loc = job.find('span', class_='rgt-area').get_text(strip=True) if job.find('span', class_='rgt-area') else ""
        hd_job_num = ""  # No job number info available in the provided HTML
        hd_job_category = ""  # No job category info available in the provided HTML
        if '实习' in announcement_name:
            hd_hopeworktype = "实习"
        else:
            hd_hopeworktype = ""
        job_list.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category,
            "hd_hopeworktype": hd_hopeworktype
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
