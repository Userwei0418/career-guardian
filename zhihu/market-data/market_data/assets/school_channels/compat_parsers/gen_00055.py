
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    announcements = []

    for li in soup.select('ul.ullist > li'):
        link_tag = li.find('a')
        date_div = li.find('div', class_='date')

        if link_tag and date_div:
            announcement_name = link_tag.get_text(strip=True)
            publish_time = date_div.get_text(strip=True)
            link = link_tag['href']

            announcements.append({
                'announcement_name': announcement_name,
                'publish_time': publish_time,
                'link': link
            })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(announcements, f, ensure_ascii=False, indent=4)