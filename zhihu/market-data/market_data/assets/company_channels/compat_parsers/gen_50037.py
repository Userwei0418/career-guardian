import json
from bs4 import BeautifulSoup


def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for card in soup.find_all('div', class_='list-card-item1'):
        announcement_name_elem = card.find('span', class_='top-label')
        announcement_name = announcement_name_elem.text.strip() if announcement_name_elem else ''

        publish_time_elem = card.find('span', class_='pub-time')
        publish_time = publish_time_elem.text.replace('发布时间：', '').strip() if publish_time_elem else ''

        # 构造完整详情页链接
        card_id = card.get('id', '')
        link = ""

        hd_dept = ''  # HTML里没有提供部门
        hd_loc_elem = card.find('span', class_='work-place')
        hd_loc = hd_loc_elem.text.strip().replace('|', '') if hd_loc_elem else ''

        hd_job_num_elem = card.find('span', class_='need-people')
        hd_job_num = hd_job_num_elem.text.replace('招聘人数：', '').strip() if hd_job_num_elem else ''

        hd_job_category_elem = card.find('span', class_='pos-cate')
        hd_job_category = hd_job_category_elem.text.strip() if hd_job_category_elem else ''

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
