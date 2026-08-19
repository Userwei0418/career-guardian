
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_cards = soup.find_all('div', class_='job-card')
    
    job_list = []
    
    for job in job_cards:
        announcement_name = job.find('a', class_='name').text.strip()
        publish_time = job.find('span', class_='update-time').text.split(' ')[0]
        link = job.find('a', class_='name')['href']
        hd_dept = ""
        hd_loc = ""
        hd_job_num = "不限"  # Assuming a placeholder for job number as it's not provided in the HTML
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
