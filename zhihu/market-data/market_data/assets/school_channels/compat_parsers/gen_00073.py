
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    items = soup.select('#data_html .item')

    result = []

    for item in items:
        announcement_name = item.find('a').get('title')
        publish_time = item.find('span', class_='item-time').text.strip()
        link = item.find('a').get('href')
        # hd_company = item.find('a').text.strip()

        result.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link#,
            # "hd_company": hd_company
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=4)