import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    items = soup.select('.pub-list .item')

    results = []

    for item in items:
        announcement_name = item.select_one('.item-tit .item-link').get('title')
        publish_time = item.select_one('.item-other .io-inner .io-text').text.strip()
        link = item.select_one('.item-tit .item-link').get('href')

        results.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=4)