
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')

    # announcement_name = soup.find('h2').find('a').text.strip()
    items = []

    for li in soup.find_all('li'):
        announcement_name = li.find('a').text.strip()
        publish_time = li.find('span').text.strip()
        link = li.find('a')['href']
        link = f"{link}"  # Assuming a base URL for the links
        announcement_title = li.find('a').text.strip()

        items.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(items, f, ensure_ascii=False, indent=4)