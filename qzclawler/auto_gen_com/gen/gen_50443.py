
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    job_elements = soup.find_all('div', class_='link-2tgd22te-3')
    
    for job in job_elements:
        title = job.find('div', class_='title-20V7ljm-Id').get_text(strip=True)
        publish_time = job.find('span', class_='opened-at-20H_gh2Tqd').get_text(strip=True).replace('发布时间：', '')
        link = job.find('a')['href']
        department =""
        job_category = ""
        job_num = ""
        location = ""

        job_info = {
            "announcement_name": title,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": department,
            "hd_loc": location,
            "hd_job_num": job_num,
            "hd_job_category": job_category
        }
        
        job_list.append(job_info)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
