
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    positions = []

    for position in soup.find_all('div', class_='position_list'):
        position_name = position.find('div', class_='position_name').text.strip()
        position_tags = position.find('div', class_='position_tag').find_all('div')
        
        if len(position_tags) >= 4:
            hd_loc = position_tags[0].text.strip()
            hd_dept = position_tags[1].text.strip()
            hd_job_num = position_tags[2].text.strip()
            hd_job_category = position_tags[3].text.strip()
            
            positions.append({
                "announcement_name": position_name,
                "publish_time": "",  # Placeholder as no publish time is provided in the HTML
                "link": "",          # Placeholder as no link is provided in the HTML
                "hd_dept": hd_dept,
                "hd_loc": hd_loc,
                "hd_job_num": "",
                "hd_job_category": ""
            })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(positions, f, ensure_ascii=False, indent=4)
