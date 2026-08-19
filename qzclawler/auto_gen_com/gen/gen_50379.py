
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    position_items = soup.find_all('div', class_='position-item')
    
    for item in position_items:
        announcement_name = item.find('strong').text.strip()
        publish_time = item.find('div', class_='ivva-color-999').text.strip().replace('发布于', '')
        link = item.find('a')['href']
        
        # Extracting department, location, job number, and job category
        other_info = item.find('div', class_='other-info').text.strip().split(' ')
        hd_loc = other_info[0] if len(other_info) > 0 else ''
        hd_dept = ''  # Assuming department info is not available in the provided HTML
        hd_job_num = ''  # Assuming job number info is not available in the provided HTML
        hd_job_category = ''  # Assuming job category info is not available in the provided HTML
        
        job_list.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
