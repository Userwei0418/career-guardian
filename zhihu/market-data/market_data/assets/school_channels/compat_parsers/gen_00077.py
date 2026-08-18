
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    announcements = []

    for li in soup.find_all('li'):
        a_tag = li.find('a')
        if a_tag:
            link = a_tag['href']
            publish_time = a_tag.find('span').get_text(strip=True)
            #移除span
            a_tag.find('span').decompose()
            announcement_name = a_tag.get_text(strip=True)
            hd_company = ""#announcement_name.split(' ')[1] if len(announcement_name.split(' ')) > 1 else ''

            announcements.append({
                "announcement_name": announcement_name,
                "publish_time": publish_time,
                "link": link
                # "hd_company": hd_company
            })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(announcements, f, ensure_ascii=False, indent=4)