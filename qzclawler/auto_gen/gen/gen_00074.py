
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    announcements = []

    for li in soup.select('ul.list.norm li'):
        announcement_name = li.select_one('div.left-text span.list-font-style').get('title')
        publish_time = li.select_one('span.right-text').text.strip()
        link = ''  # Assuming no link is provided in the HTML
        hd_company = ''  # Assuming no company name is provided in the HTML

        announcements.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_company": hd_company
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(announcements, f, ensure_ascii=False, indent=4)