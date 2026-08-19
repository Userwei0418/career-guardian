
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for job in soup.find_all('div', class_='recruit-list'):
        title = job.find('span', class_='job-recruit-title').text.strip()
        location = job.find('span', class_='job-recruit-location').text.strip()
        tips = job.find('p', class_='recruit-tips').find_all('span')
        department = tips[0].text.strip()
        category = tips[1].text.strip()
        experience = tips[2].text.strip()
        publish_time = tips[3].text.strip()
        
        job_info = {
            "announcement_name": title,
            "publish_time": publish_time,
            "link": "",  # Assuming link is not provided in the HTML
            "hd_dept": department,
            "hd_loc": location,
            "hd_job_num": "",  # Assuming experience is used as job number
            "hd_job_category": category
        }
        
        job_list.append(job_info)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
