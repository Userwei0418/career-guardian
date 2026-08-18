
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    announcements = []

    for announcement in soup.find_all('div', class_='announcement'):
        announcement_name = announcement.find('p', class_='announcement-right-header').get_text(strip=True)
        publish_time = announcement.find('p', class_='announcement-left-time').get_text(strip=True)
        link = announcement.find('a')['href'] if announcement.find('a') else None  # Assuming there's a link, adjust if necessary

        announcements.append({
            'announcement_name': announcement_name,
            'publish_time': publish_time,
            'link': link
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(announcements, f, ensure_ascii=False, indent=4)