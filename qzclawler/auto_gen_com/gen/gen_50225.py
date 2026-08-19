
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    items = soup.find_all('div', class_='list-container-item')
    
    result = []
    
    for item in items:
        title_div = item.find('div', class_='list-container-item-title')
        date_span = title_div.find('span', class_='list-container-item-date')
        tags_div = item.find('div', class_='list-container-item-tags')
        
        announcement_name = title_div.text.replace(date_span.text, '').strip()
        publish_time = date_span.text.strip()
        link = ''  # Assuming no link is provided in the HTML
        hd_dept = tags_div.contents[0].strip()
        hd_loc = tags_div.contents[2].strip()
        hd_job_num = tags_div.contents[4].strip()
        hd_job_category = tags_div.contents[6].strip() if len(tags_div.contents) > 6 else ''
        
        result.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        })
    
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=4)
