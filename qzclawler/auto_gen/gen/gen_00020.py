
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    announcements = []

    info_items = soup.find_all('div', class_='infoItem')
    for item in info_items:
        title_tag = item.find('a', class_='tit')
        title = title_tag.get('title', '')
        link = title_tag.get('href', '')
        time_tag = item.find('span', class_='time')
        publish_time = time_tag.get_text(strip=True) if time_tag else ''

        announcements.append({
            'announcement_name': title,
            'publish_time': publish_time,
            'link': link
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(announcements, f, ensure_ascii=False, indent=4)