
import json
from bs4 import BeautifulSoup
import datetime

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    announcements = []

    for li in soup.select('ul.home-hot-sxh li'):
        a_tag = li.find('a')
        announcement_name = a_tag.find('div', class_='title').get_text(strip=True)
        link = a_tag['href']
        publish_time = ""  # Assuming publish_time is not available in the provided HTML
        #获取当前日期
        current_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        publish_time = current_date

        announcements.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(announcements, f, ensure_ascii=False, indent=4)