
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    announcements = []

    for item in soup.select('#zczph_list_ul li'):
        link_tag = item.find('a')
        if link_tag:
            announcement_name = link_tag.find('div', class_='cont').text.strip()
            publish_time = link_tag.find('div', class_='lab').find('p', class_='shijian').text.replace('举办日期：', '').strip()
            #publish_time只要年月日
            publish_time = publish_time.split(' ')[0]
            hd_company = announcement_name.split('【')[-1].replace('】', '').strip()
            link = link_tag['onclick'].split("'")[1]  # Extracting the ID from the onclick function

            announcements.append({
                "announcement_name": announcement_name,
                "publish_time": publish_time,
                "link": "",
                "hd_company": hd_company
            })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(announcements, f, ensure_ascii=False, indent=4)