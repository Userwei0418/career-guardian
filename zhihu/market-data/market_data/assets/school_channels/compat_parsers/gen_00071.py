
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    items = soup.find_all('div', class_='item')

    result = []

    for item in items:
        announcement_name = item.find('div', class_='ic-title').find('a').text.strip()
        publish_time = item.find('div', class_='ir-time').text.strip()
        link = item.find('div', class_='ic-title').find('a')['href']
        hd_company = item.find('div', class_='ic-sub').find_all('span')[-1].text.strip()

        result.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_company": hd_company
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=4)