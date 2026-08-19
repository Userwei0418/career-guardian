
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    positions = []
    
    for item in soup.find_all('div', class_='position-list-item'):
        title = item.find('div', class_='position-list-item-top').text.strip()
        details = item.find('div', class_='position-list-item-bottom').find_all('span')
        
        if len(details) >= 5:
            location = details[0].text.strip()
            experience = details[2].text.strip()
            publish_time = details[6].text.strip().replace('更新于 ', '')
        else:
            location = experience = publish_time = ''
        
        position = {
            "announcement_name": title,
            "publish_time": publish_time,
            "link": "",  # Placeholder for link, as it's not provided in the HTML
            "hd_dept":"" ,
            "hd_loc": location,
            "hd_job_num": "1",
            "hd_job_category": ""  # Placeholder for job category, as it's not provided in the HTML
        }
        
        positions.append(position)
    
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(positions, f, ensure_ascii=False, indent=4)
