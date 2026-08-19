
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    announcements = []

    for row in soup.find_all('div', class_='row'):
        title_tag = row.find('h3').find('a')
        publish_time_tag = row.find('ul', class_='blog-tag-data').find('li').i.find_next_sibling(text=True)
        
        if title_tag and publish_time_tag:
            announcement_name = title_tag.get_text(strip=True)
            publish_time = publish_time_tag.split('：')[1].strip()  # Get the date after ' 发表于：'
            link = title_tag['href']

            announcements.append({
                'announcement_name': announcement_name,
                'publish_time': publish_time,
                'link': link
            })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(announcements, f, ensure_ascii=False, indent=4)