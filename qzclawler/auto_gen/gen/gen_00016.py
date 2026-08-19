import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    announcements = []
    
    for div in soup.select('.zpxxList'):
        announcement_name = div.select_one('.zpxxUnitNature').text.strip()
        publish_time = div.select_one('.zpxxUnitTime').text.strip()
        link = div.parent['onclick'].split("'")[1]  # Extracting the ID from the onclick attribute
        link = f"/career/zpxx/view/zpxx/{link}"  # Assuming the link format based on ID
        
        announcements.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link
        })
    
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(announcements, f, ensure_ascii=False, indent=4)