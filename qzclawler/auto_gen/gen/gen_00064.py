
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    table_rows = soup.select('#bodylist tr')
    
    announcements = []
    
    for row in table_rows:
        announcement_name = row.find('td').get_text(strip=True)
        link = row.find('a')['href']
        publish_time = row.find_all('td')[1].get_text(strip=True)
        
        announcements.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link
        })
    
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(announcements, f, ensure_ascii=False, indent=4)