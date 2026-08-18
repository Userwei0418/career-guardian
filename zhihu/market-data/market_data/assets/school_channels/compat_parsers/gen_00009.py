import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    announcements = []

    for item in soup.select('.list.online.article .list-item'):
        link = item.find('a', class_='item-link')['href']
        announcement_name = item.find('span', class_='item-link-title').get_text(strip=True)
        publish_time = item.find('span', class_='item-link-date').get_text(strip=True)

        announcements.append({
            'announcement_name': announcement_name,
            'publish_time': publish_time,
            'link': link
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(announcements, f, ensure_ascii=False, indent=4)