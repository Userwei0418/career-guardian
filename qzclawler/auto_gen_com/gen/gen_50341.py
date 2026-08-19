
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_table = soup.find('dl', class_='m-table_info')
    jobs = []

    for dd in job_table.find_all('dd'):
        job_link = dd.find('a', class_='j-job')
        announcement_name = job_link.find('span', class_='item_1').text.strip()
        hd_job_num = job_link.find('span', class_='item_2').text.strip()
        hd_job_category = job_link.find('span', class_='item_3').text.strip()
        hd_loc = job_link.find_all('span', class_='item_3')[1].text.strip()
        
        job_data = {
            "announcement_name": announcement_name,
            "publish_time": "",  # Assuming publish_time is not available in the provided HTML
            "link": job_link['href'],
            "hd_dept": "",  # Assuming hd_dept is not available in the provided HTML
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": ""
        }
        
        jobs.append(job_data)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(jobs, f, ensure_ascii=False, indent=4)
