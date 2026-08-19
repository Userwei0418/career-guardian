
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    departments = soup.find_all('div', {'data-testid': 'department'})
    
    for department in departments:
        hd_dept = department.h3.get_text(strip=True)
        job_items = department.find_all('div', recursive=False)
        
        for job in job_items:
            link = job.a['href']
            announcement_name = job.a.get_text(strip=True)
            hd_loc = job.p.get_text(strip=True)
            hd_job_num = ""  # Placeholder as the number of jobs is not specified in the HTML
            hd_job_category = ""  # Placeholder as the job category is not specified in the HTML
            publish_time = ""  # Placeholder as the publish time is not specified in the HTML
            
            job_list.append({
                "announcement_name": announcement_name,
                "publish_time": publish_time,
                "link": link,
                "hd_dept": hd_dept,
                "hd_loc": hd_loc,
                "hd_job_num": hd_job_num,
                "hd_job_category": hd_job_category
            })

    with open(tempfile, 'w') as json_file:
        json.dump(job_list, json_file, ensure_ascii=False, indent=4)
