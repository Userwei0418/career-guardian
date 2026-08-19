
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
            publish_time = footer_div.find('span', class_='pub-time').text.replace('发布时间：', '')
            hd_job_num = footer_div.find('span', class_='need-people').text.replace('招聘人数：', '')
            hd_dept = summary_div.find_all('span')[1].get('title', '') if len(summary_div.find_all('span')) > 1 else ''
            hd_loc = summary_div.find_all('span')[1].text if len(summary_div.find_all('span')) > 1 else ''
            hd_job_category = summary_div.find('span').text if summary_div.find('span') else ''

            job_list.append({
                "announcement_name": announcement_name,
                "publish_time": publish_time,
                "link": "",  # Assuming no link is provided in the HTML
                "hd_dept": hd_dept,
                "hd_loc": hd_loc,
                "hd_job_num": hd_job_num,
                "hd_job_category": hd_job_category
            })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
