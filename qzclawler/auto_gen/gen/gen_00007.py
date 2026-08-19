import json
from bs4 import BeautifulSoup

def extract_table_from_html(html_context, temp_file):
    soup = BeautifulSoup(html_context, 'html.parser')
    announcements = []

    for card in soup.find_all('div', class_='ant-pro-card'):
        title_div = card.find('div', class_='ant-card-head-title')
        if title_div:
            announcement_name = title_div.get_text(strip=True)
            ann_div = title_div.find("div", class_="ant-col ant-col-24")
            if ann_div:
                announcement_name = ann_div.get_text(strip=True)
            publish_time_div = card.find('div', style=lambda x: x and 'margin-bottom: 5px; float: right; color: rgba(0, 0, 0, 0.85)' in x)
            if publish_time_div:
                publish_time = publish_time_div.get_text(strip=True)
            else:
                publish_time = None
            link_div = card.find('div', class_='ant-list-item-meta-title')
            link = link_div.find('a')['href'] if link_div and link_div.find('a') else None
            
            announcements.append({
                'announcement_name': announcement_name,
                'publish_time': publish_time,
                'link': link
            })

    with open(temp_file, 'w', encoding='utf-8') as f:
        json.dump(announcements, f, ensure_ascii=False, indent=4)