import json
from bs4 import BeautifulSoup
import re

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    items = soup.select('.noticelist ul li a')
    data_list = []
    for item in items:
        #如果没有标题属性，则跳过
        if not item.has_attr('title'):
            continue
        link = item['href']
        title = item['title']
        time_str = item.select_one('.time').get_text(strip=True)
        publish_time = re.search(r'\[(\d{4}-\d{2}-\d{2})\]', time_str).group(1) if time_str else ''
        data_list.append({
            "announcement_name": title,
            "publish_time": publish_time,
            "link": link
        })
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(data_list, f, ensure_ascii=False, indent=2)