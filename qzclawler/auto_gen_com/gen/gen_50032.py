import json
import requests
from bs4 import BeautifulSoup


def extract_table_from_html(htmlcontext, tempfile):



    # 解析 HTML
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for card in soup.find_all('div', class_='card-item-wrap'):
        title_div = card.find('div', class_='pos-title-item')
        category_span = card.find('span', class_='pos-cate')
        summary_div = card.find('div', class_='pos-summary')
        pub_time_span = card.find('span', class_='pub-time')
        need_people_span = card.find('span', class_='need-people')

        announcement_name = title_div.get('title', '') if title_div else ''
        hd_dept = category_span.get('title', '') if category_span else ''
        hd_loc = summary_div.get('title', '') if summary_div else ''
        publish_time = pub_time_span.text.replace('发布时间：', '') if pub_time_span else ''
        hd_job_num = need_people_span.text.replace('招聘人数：', '') if need_people_span else ''
        hd_job_category = hd_dept

        # 获取链接（如果映射里有）

        link = ""

        job_list.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        })

    # 保存文件
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)

