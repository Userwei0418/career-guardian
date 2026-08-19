
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    job_elements = soup.find_all('div', class_='_2AOmjKmlEtuR_KEoehWYcN')
    
    for job in job_elements:
        announcement_name = job.find('div', class_='_1RRlPtjyYmeDGCWt9lrk2P').text.strip().replace("/",',')
        publish_time = job.find('div', class_='_3Jn5Z6PZA5H7Auzy0xlXu2').text.replace('更新于 ', '').strip()
        hd_loc = job.find('div', class_='_3CJNtKfv5mLnNfeqL1jgRB').text.strip()
        
        job_info = {
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": "",  # Link is not provided in the HTML snippet
            "hd_dept": "",  # Department is not specified in the HTML snippet
            "hd_loc": hd_loc,
            "hd_job_num": "",  # Job number is not specified in the HTML snippet
            "hd_job_category": ""  # Job category is not specified in the HTML snippet
        }
        
        job_list.append(job_info)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
