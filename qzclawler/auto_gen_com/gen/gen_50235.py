
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    job_elements = soup.find_all('div', class_='_2AOmjKmlEtuR_KEoehWYcN')
    
    for job in job_elements:
        announcement_name = job.find('div', class_='_1RRlPtjyYmeDGCWt9lrk2P').text.strip()
        publish_time = job.find('div', class_='_3Jn5Z6PZA5H7Auzy0xlXu2').text.replace('更新于 ', '').strip()
        hd_loc = job.find('div', class_='_3CJNtKfv5mLnNfeqL1jgRB').text.strip().replace('/',',')
        
        job_info = {
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": "",  # Assuming no link is provided in the HTML
            "hd_dept": "",  # Assuming the department is constant
            "hd_loc": hd_loc,
            "hd_job_num": "1",  # Assuming no job number is provided in the HTML
            "hd_job_category": ""  # Assuming no job category is provided in the HTML
        }
        
        job_list.append(job_info)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
