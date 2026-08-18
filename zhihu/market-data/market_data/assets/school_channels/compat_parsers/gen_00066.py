
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    announcements = []

    for li in soup.find_all('li'):
        link_tag = li.find('a')
        if link_tag:
            announcement_name = link_tag.get_text(strip=True)
            link = link_tag['href']
            publish_time = li.find('span').get_text(strip=True)
            announcements.append({
                "announcement_name": announcement_name,
                "publish_time": publish_time,
                "link": link
            })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(announcements, f, ensure_ascii=False, indent=4)