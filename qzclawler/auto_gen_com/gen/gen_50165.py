
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for card in soup.find_all('div', class_='card-item-wrap'):
        announcement_name = card.find('span', class_='top-label').text.strip()
        publish_time = card.find('span', class_='pub-time').text.replace('发布时间：', '').strip()
        link = ""
        hd_dept = ""  # Placeholder as the department is not provided in the HTML
        hd_loc = card.find('span', class_='work-place').text.strip().replace('|', '')
        hd_job_num = card.find('span', class_='need-people').text.replace('招聘人数：', '').strip()
        hd_job_category = card.find('span', class_='pos-cate').text.strip()

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
