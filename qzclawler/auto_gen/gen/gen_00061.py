
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    announcements = []

    for item in soup.find_all('li', class_='columnItem'):
        title_tag = item.find('span', class_='news_title').find('a')
        date_tag = item.find('span', class_='news_date')

        announcement_name = title_tag.get('title')
        publish_time = date_tag.text.strip()
        link = title_tag.get('href')

        announcements.append({
            'announcement_name': announcement_name,
            'publish_time': publish_time,
            'link': link
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(announcements, f, ensure_ascii=False, indent=4)