import json
from bs4 import BeautifulSoup
import re

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    announcements = []

    for li in soup.select('ul.cons > li'):
        a_tag = li.find('a')
        if a_tag:
            announcement_name = a_tag.get_text(strip=True)  # Skip the [置顶] part
            pattern = r"(\d{4}-\d{2}-\d{2})"
            parts = re.split(pattern, announcement_name)
            if len(parts)>1:
                announcement_name = parts[0]

            publish_time = a_tag.find('i', class_='list-time').get_text(strip=True)
            link = a_tag['href']
            announcements.append({
                "announcement_name": announcement_name,
                "publish_time": publish_time,
                "link": link
            })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(announcements, f, ensure_ascii=False, indent=4)