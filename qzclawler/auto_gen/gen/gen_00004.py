import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    announcements = []

    for li in soup.find_all('li'):
        a_tag = li.find('a')
        if a_tag:
            # announcement_name = a_tag.get_text(strip=True)
            publish_time = a_tag.find('i', class_='list-time').get_text(strip=True)
            link = a_tag['href']
            #清除掉不用的
            # 移除日期和次数的 <i> 标签
            for i_tag in a_tag.find_all('i'):
                i_tag.extract()
            announcement_name = a_tag.get_text(strip=True)
            announcements.append({
                "announcement_name": announcement_name,
                "publish_time": publish_time,
                "link": link
            })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(announcements, f, ensure_ascii=False, indent=4)