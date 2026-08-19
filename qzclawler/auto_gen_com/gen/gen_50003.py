import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []


    for card in soup.find_all('div', class_='list-card-item1'):
        announcement_name = card.find('span', class_='top-label').text.strip()
        publish_time = ''  # 页面中没有发布时间，这里留空
        hd_loc = card.find('span', class_='work-place').text.strip().replace('|', '')
        hd_job_num_tag = card.find('span', class_='need-people')
        hd_job_num = hd_job_num_tag.text.replace('招聘人数：', '').strip() if hd_job_num_tag else ''
        hd_job_category = card.find('span', class_='pos-cate').text.strip()
        hd_dept = ''  # 页面无此字段，保持空字符串

        # 这里是重点，获取div的id，拼接成link
        post_id = card.get('id')
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

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
