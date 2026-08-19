
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    job_elements = soup.find_all('div', class_='link-2tgd22te-3')
    
    for job in job_elements:
        link = job.find('a')['href']
        title = job.find('div', class_='title-20V7ljm-Id').get_text(strip=True).replace('急','')
        status_items = job.find_all('span', class_='status-item-1_w5ygMyMO')
        location = job.find('div', class_='locations-32aEgVWFz_').get_text(strip=True)
        publish_time = job.find('span', class_='opened-at-20H_gh2Tqd').get_text(strip=True).replace('发布时间：', '')

        announcement_name = title
        hd_dept = status_items[0].get_text(strip=True) if len(status_items) > 0 else ''
        hd_job_category = status_items[1].get_text(strip=True) if len(status_items) > 1 else ''
        hd_loc = location
        hd_job_num = ''  # Placeholder as the job number is not provided in the HTML
        hd_job_num = ''  # Placeholder as the job number is not provided in the HTML

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
