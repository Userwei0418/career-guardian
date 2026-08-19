
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    position_items = soup.find_all('div', class_='position-list-item')
    
    result = []
    
    for item in position_items:
        title = item.find('div', class_='position-list-item-top').text.strip()
        bottom_info = item.find('div', class_='position-list-item-bottom').find_all('span')
        
        location = bottom_info[0].text.strip()
        job_category = bottom_info[2].text.strip()
        publish_time = bottom_info[4].text.strip().replace('更新于 ', '')
        
        # Assuming the link and other fields are not available in the provided HTML
        link = ""  # Placeholder for link
        hd_dept = ""  # Placeholder for department
        hd_loc = location
        hd_job_num = ""  # Placeholder for job number
        
        result.append({
            "announcement_name": title,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": job_category
        })
    
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=4)
