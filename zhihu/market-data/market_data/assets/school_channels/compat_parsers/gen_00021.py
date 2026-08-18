
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    results = []

    for li in soup.select('.zpxx li'):
        announcement_name = li.select_one('.l a.up').text.strip()
        publish_time = li.select_one('.r').text.strip()
        link = li.select_one('.l a.up')['href']

        results.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=4)