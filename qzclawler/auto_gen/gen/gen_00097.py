
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    announcements = []
    
    for li in soup.select('ul.ul_list.ul_qh1 li'):
        publish_time = li.find('span').text.strip()
        link_tag = li.find_all('a')[1]
        announcement_name = link_tag.text.strip()
        link = link_tag['href']
        hd_company = link_tag.get('title', '').split(' ')[0]  # Extract company name from title if available
        
        announcements.append({
            'announcement_name': announcement_name,
            'publish_time': publish_time,
            'link': link,
            'hd_company': hd_company
        })
    
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(announcements, f, ensure_ascii=False, indent=4)