
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    announcements = []
    
    for li in soup.select('ul.uli14 li'):
        announcement_name = li.a.get('title')
        publish_time = li.find('span', class_='time').text.strip()
        link = li.a.get('href')
        hd_company = ""#announcement_name.split('拟聘人员公示')[0]  # Extract company name from announcement name
        
        announcements.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_company": hd_company
        })
    
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(announcements, f, ensure_ascii=False, indent=4)