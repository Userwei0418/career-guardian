
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    announcements = []

    for item in soup.find_all('div', class_='zhaopin-wrap hover-item'):
        title = item.find('div', class_='zhaopin-item-title').get_text(strip=True)
        tag_info = item.find('div', class_='zhaopin-item-tag').get_text(strip=True).split(' ')
        publish_time = tag_info[0]
        hd_company = ""#tag_info[-1]  # Assuming the last part is the company name
        link = ''  # Placeholder for link, as the provided HTML does not contain links

        announcements.append({
            'announcement_name': title,
            'publish_time': publish_time,
            'link': link
            # 'hd_company': hd_company
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(announcements, f, ensure_ascii=False, indent=4)