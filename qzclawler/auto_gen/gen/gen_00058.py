
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    announcements = []

    for li in soup.find_all('li'):
        a_tag = li.find('a')
        if a_tag: 
            publish_time = a_tag.find('span').text.strip()
            link = a_tag['href']
            for span in a_tag.find_all('span'):
                span.extract()
            announcement_name = a_tag.text.strip()
            announcements.append({
                "announcement_name": announcement_name,
                "publish_time": publish_time,
                "link": link
            })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(announcements, f, ensure_ascii=False, indent=4)