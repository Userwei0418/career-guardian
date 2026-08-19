
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for card in soup.find_all('div', class_='card-item-wrap'):
        title_div = card.find('div', class_='pos-title-item')
        category_span = card.find('span', class_='pos-cate')
        summary_div = card.find('div', class_='pos-summary')
        pub_time_span = card.find('span', class_='pub-time')
        need_people_span = card.find('span', class_='need-people')

        announcement_name = title_div.get('title') if title_div else None
        hd_dept = summary_div.get('title').split('|')[0].strip() if summary_div else None
        hd_loc = summary_div.get('title').split('|')[1].strip() if summary_div else None
        publish_time = pub_time_span.text.replace('发布时间：', '') if pub_time_span else None
        hd_job_num = need_people_span.text.replace('招聘人数：', '') if need_people_span else None
        hd_job_category = category_span.get('title') if category_span else None
        link = ''  # Assuming no link is provided in the HTML

        job_list.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
