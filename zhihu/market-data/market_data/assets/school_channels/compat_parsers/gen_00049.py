
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    announcements = []

    for item in soup.find_all('li', class_='list-item ant-list-item'):
        title_tag = item.find('div', class_='blue-label')
        link_div = item.find('div', class_='top-left')
        link_tag = link_div.find('a')
        time_tag = item.find('span', class_='grey-label')


        com_div = item.find('div', class_='top-middle')
        com_tag = com_div.find('div', class_='blue-label')
        com_name = com_tag.get_text(strip=True)

        announcement_name = title_tag.get_text(strip=True)
        link = link_tag['href'] if link_tag else None
        publish_time = time_tag.get_text(strip=True).replace('发布于：', '')

        announcements.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_company": com_name
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(announcements, f, ensure_ascii=False, indent=4)