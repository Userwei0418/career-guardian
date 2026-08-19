import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    announcements = []
    
    items = soup.select('#data_html .item')
    for item in items:
        announcement_name = item.select_one('.item-text a').get('title')
        publish_time = item.select_one('.item-time').text.strip()
        link = item.select_one('.item-text a').get('href')
        
        announcements.append({
            'announcement_name': announcement_name,
            'publish_time': publish_time,
            'link': link
        })
    
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(announcements, f, ensure_ascii=False, indent=4)