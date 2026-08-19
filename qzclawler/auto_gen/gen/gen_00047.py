
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    announcements = []

    for li in soup.select('ul.list2 li'):
        a_tag = li.find('a')
        title = a_tag.find('div', class_='title').text.strip()
        date = a_tag.find('div', class_='date').text.strip()
        link = a_tag['href']
        
        announcements.append({
            'announcement_name': title,
            'publish_time': date,
            'link': link
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(announcements, f, ensure_ascii=False, indent=4)