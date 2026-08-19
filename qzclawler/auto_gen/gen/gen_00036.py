
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    announcements = []

    for li in soup.select('ol.ollist > li'):
        a_tag = li.find('a', class_='lista')
        announcement_name = a_tag['title']
        publish_time = a_tag.find('div', class_='ol_left').find('span').text.strip()
        link = a_tag['href']
        
        announcements.append({
            'announcement_name': announcement_name,
            'publish_time': publish_time,
            'link': link
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(announcements, f, ensure_ascii=False, indent=4)