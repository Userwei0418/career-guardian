
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for card in soup.find_all('div', class_='card-item-wrap'):
        title_div = card.find('div', class_='pos-title-item')
        summary_div = card.find('div', class_='pos-summary')
        footer_div = card.find('div', class_='pos-ft')

        if title_div and summary_div and footer_div:
            announcement_name = title_div.get('title', '')
            location_info = summary_div.get('title', '').split(' | ')
            publish_info = footer_div.get('title', '').split(' | ')

            job_info = {
                "announcement_name": announcement_name,
                "publish_time": publish_info[0].replace('发布时间：', ''),
                "link": "",  # Assuming no link is provided in the HTML
                "hd_dept": location_info[0] if len(location_info) > 0 else '',
                "hd_loc": location_info[1] if len(location_info) > 1 else '',
                "hd_job_num": publish_info[1].replace('招聘人数：', ''),
                "hd_job_category": ""  # Assuming no job category is provided in the HTML
            }

            job_list.append(job_info)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)