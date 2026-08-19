
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_items = soup.find_all('a', class_='PositionList__job-item')
    
    job_list = []
    
    for item in job_items:
        announcement_name = item.find('h4', class_='job-title').get('title', '') if item.find('h4', class_='job-title') else ""
        publish_time = ""  # Placeholder as the HTML does not contain this information
        link = item.get('href', '')
        hd_dept = ""  # Placeholder as the HTML does not contain this information
        hd_loc = item.find('span', class_='job-desc-item').get_text(strip=True) if item.find('span', class_='job-desc-item') else ""
        hd_job_num = ""  # Placeholder as the HTML does not contain this information
        hd_job_category = ""  # Placeholder as the HTML does not contain this information
        
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
