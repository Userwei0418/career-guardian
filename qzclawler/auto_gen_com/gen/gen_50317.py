
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    job_elements = soup.find_all('div', class_='link-2tgd22te-3')
    
    for job in job_elements:
        title = job.find('div', class_='title-20V7ljm-Id').text.strip()
        publish_time = job.find('span', class_='opened-at-20H_gh2Tqd').text.replace('发布时间：', '').strip()
        link = job.find('a')['href']
        hd_dept = ""  # Assuming this is a constant value based on the provided HTML
        hd_loc = job.find('div', class_='locations-32aEgVWFz_').text.strip()
        hd_job_num = "1"  # Assuming a constant value as the number of positions is not provided
        hd_job_category = ""  # Assuming this is the job category based on the status

        job_info = {
            "announcement_name": title,
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
