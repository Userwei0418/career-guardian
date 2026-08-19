import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile, post_type="society"):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    base_url = ""

    for card in soup.find_all('div', class_='card-item-wrap'):
        announcement_name = card.find('span', class_='top-label').text.strip()
        publish_time = card.find('span', class_='pub-time').text.replace('发布时间：', '').strip()
        post_id = card.find('div', class_='list-card-item1').get('id')  # 提取 postId
        link = ""
        hd_dept = card.find('div', class_='pos-tag-item').text.strip()
        hd_loc = card.find('span', class_='work-place').text.strip().split(' | ')[0].replace('|', '')
        hd_job_num = card.find('span', class_='need-people').text.replace('招聘人数：', '').strip()
        hd_job_category = card.find('div', class_='pos-tag-item').text.strip()

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
