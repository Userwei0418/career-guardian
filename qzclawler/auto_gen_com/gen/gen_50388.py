
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_items = soup.find_all('div', class_='job-item active')
    
    job_list = []
    
    for job in job_items:
        title = job.find('div', class_='job-title').span.text.strip()
        date_info = job.find('div', class_='job-date').text.strip()
        publish_time = date_info.split(' ')[0]  # Extracting the date part
        link = job.find('div', class_='details-button').a['href']
        dept = job.find('div', class_='job-location').text.strip()
        loc = dept.split('：')[1] if '：' in dept else dept  # Extracting location
        job_num = ""  # Placeholder as job number is not provided in the HTML
        job_category = job['data-classification']
        
        job_list.append({
            "announcement_name": title,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": dept,
            "hd_loc": loc,
            "hd_job_num": job_num,
            "hd_job_category": job_category
        })
    
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
