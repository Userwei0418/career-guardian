
import json
from bs4 import BeautifulSoup

def extract_table_from_html(html_content, temp_file):
    soup = BeautifulSoup(html_content, 'html.parser')
    announcements = []

    for li in soup.select('#zpxx-list-content li'):
        announcement_name = li.find('a', class_='texth').text.strip()
        publish_time = li.find('span', class_='floatR time').text.strip().replace('时间', '')
        link = li.find('a', class_='texth')['href']

        announcements.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link
        })

    with open(temp_file, 'w', encoding='utf-8') as f:
        json.dump(announcements, f, ensure_ascii=False, indent=4)