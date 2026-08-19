
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for card in soup.find_all('div', class_='card-item-wrap'):
        title_div = card.find('div', class_='pos-title-item')
        category_span = card.find('span', class_='pos-cate')
        summary_div = card.find('div', class_='pos-summary')
        footer_div = card.find('div', class_='pos-ft')

        announcement_name = title_div.get('title', '').strip() if title_div else ''
        hd_dept = summary_div.contents[0].text.strip() if summary_div else ''
        hd_loc = summary_div.contents[1].text.strip() if len(summary_div.contents) > 1 else ''
        publish_time = footer_div.find('span', class_='pub-time').text.replace('发布时间：', '').strip() if footer_div else ''
        hd_job_num = footer_div.find('span', class_='need-people').text.replace('招聘人数：', '').strip() if footer_div else ''
        hd_job_category = category_span.get('title', '').strip() if category_span else ''

        job_list.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": "",  # Link is not provided in the HTML snippet
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
