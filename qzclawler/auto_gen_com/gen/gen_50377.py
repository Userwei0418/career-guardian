import json
from bs4 import BeautifulSoup


def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')

    # 1. 找到“职位卡片”型 <a>
    job_items = []
    for a in soup.find_all('a'):
        if a.find('div', class_='uk-grid'):
            job_items.append(a)

    job_list = []

    for item in job_items:
        strong = item.find('strong')
        if strong is None:    # double check，避免脏数据
            continue

        job_name = strong.get_text(strip=True)
        link = item.get('href', '')

        job_info = {
            "announcement_name": job_name,
            "publish_time": "",
            "link": link,
            "hd_dept": "",
            "hd_loc": "",
            "hd_job_num": "",
            "hd_job_category": ""
        }

        job_list.append(job_info)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
