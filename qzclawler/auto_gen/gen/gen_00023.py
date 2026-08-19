
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    announcements = []

    for li in soup.select('.content ul li'):
        date_div = li.select_one('.date')
        day = date_div.select_one('.day').text
        year = date_div.select_one('.year').text.strip()
        publish_time = f"{year}.{day}"

        title_div = li.select_one('.title1 a')
        announcement_name = title_div.text.strip()
        link = title_div['href']

        announcements.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(announcements, f, ensure_ascii=False, indent=4)