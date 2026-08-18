
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    announcements = []

    for item in soup.find_all('li', class_='kjrkItem'):
        announcement_name = item.find('p').text.strip()
        publish_time = item.find('i', class_='time').text.strip()
        link = ''  # Assuming no link is provided in the HTML structure

        announcements.append({
            'announcement_name': announcement_name,
            'publish_time': publish_time,
            'link': link
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(announcements, f, ensure_ascii=False, indent=4)