import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    news_list = []

    for ul in soup.find_all('ul', class_='newsList'):
        publish_time = ul.find('li', class_='span2 y').text.strip()
        announcement_name = ul.find('li', class_='span1').a.text.strip()
        link = ul.find('li', class_='span1').a['href'].strip()

        news_item = {
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link
        }
        news_list.append(news_item)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(news_list, f, ensure_ascii=False, indent=4)