
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    positions = soup.find_all('li', class_='position-item')
    
    result = []
    
    for position in positions:
        title_div = position.find('div', class_='position-title')
        name = title_div.find('span', class_='type-text').text.strip()
        category = title_div.find('div', class_='position-type').text.strip()
        
        about_divs = position.find_all('div', class_='position-about')
        dept_info = about_divs[0].find_all('span')
        hd_dept = dept_info[1].text.strip() if len(dept_info) > 1 else ''
        
        hd_loc = about_divs[2].text.split('：')[1].strip() if len(about_divs) > 2 else ''
        hd_job_num = ''  # Placeholder as the number is not provided in the HTML
        publish_time = ''  # Placeholder as the publish time is not provided in the HTML
        link = ''  # Placeholder as the link is not provided in the HTML
        
        result.append({
            "announcement_name": name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": category
        })
    
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=4)
