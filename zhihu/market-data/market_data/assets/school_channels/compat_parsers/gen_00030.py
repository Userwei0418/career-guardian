
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    announcements = []

    for li in soup.find_all('li'):
        if not li.find('h3'):
            continue
        announcement_name = li.find('h3').get_text(strip=True)
        link = li.find('a')['href']
        publish_time = li.find('section', class_='m-list-line_date').find_all('span')[0].get_text(strip=True)

        announcements.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(announcements, f, ensure_ascii=False, indent=4)