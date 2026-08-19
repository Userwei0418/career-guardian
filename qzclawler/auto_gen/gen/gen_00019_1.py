
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    announcements = []

    for item in soup.select('#zpxx_list_ul li'):
        link_tag = item.find('a')
        announcement_name = link_tag.find('span', class_='cont').text.strip()
        company_name = announcement_name.split('【')[-1].replace('】', '').strip()
        publish_time = link_tag.find('div', class_='lab').find('span', class_='date').text.strip()
        link = link_tag['onclick'].split("'")[1]  # Extracting the ID from the onclick attribute

        announcements.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": "",
            "hd_company": company_name
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(announcements, f, ensure_ascii=False, indent=4)