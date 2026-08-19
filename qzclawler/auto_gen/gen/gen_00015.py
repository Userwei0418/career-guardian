import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    announcements = []

    for newslist in soup.find_all('div', class_='newslist'):
        announcement_name = newslist.find('div', class_='newListDetails').text.strip()
        publish_time = newslist.find('div', class_='newsListTime').text.strip()
        link = newslist['onclick'].split("'")[1]  # Extract link from onclick attribute

        announcements.append({
            'announcement_name': announcement_name,
            'publish_time': publish_time,
            'link': link
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(announcements, f, ensure_ascii=False, indent=4)