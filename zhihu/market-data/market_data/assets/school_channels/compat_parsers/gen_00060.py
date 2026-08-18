
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    news_list = []

    for li in soup.select('ul.news_list li.news'):
        announcement_name = li.find('span', class_='news_title').get_text(strip=True)
        link = li.find('a')['href']
        publish_time = li.find('span', class_='news_meta').get_text(strip=True).strip('[]')

        news_list.append({
            'announcement_name': announcement_name,
            'publish_time': publish_time,
            'link': link
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(news_list, f, ensure_ascii=False, indent=4)