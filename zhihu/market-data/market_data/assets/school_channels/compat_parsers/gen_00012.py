import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    announcements = []

    for li in soup.find_all('li', class_='clearfix'):
        publish_time = li.find('span').text.strip()
        a_tag = li.find('a')
        announcement_name = a_tag.text.strip()
        link = a_tag['href']

        announcements.append({
            'announcement_name': announcement_name,
            'publish_time': publish_time,
            'link': link
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(announcements, f, ensure_ascii=False, indent=4)