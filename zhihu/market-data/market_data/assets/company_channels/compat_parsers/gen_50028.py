import json
from bs4 import BeautifulSoup


def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for card in soup.find_all('div', class_='list-card-item1'):
        # 安全地提取文本内容
        announcement_name_elem = card.find('span', class_='top-label')
        announcement_name = announcement_name_elem.text.strip() if announcement_name_elem else ""

        hd_dept_elem = card.find('span', class_='pos-summary')
        hd_dept = hd_dept_elem.contents[0].strip() if hd_dept_elem and hd_dept_elem.contents else ""

        hd_loc_elem = card.find('span', class_='work-place')
        hd_loc = hd_loc_elem.text.strip().replace('|', '') if hd_loc_elem else ""

        hd_job_num_elem = card.find('span', class_='need-people')
        hd_job_num = hd_job_num_elem.text.replace('招聘人数：', '').strip() if hd_job_num_elem else ""

        hd_job_category_elem = card.find('span', class_='pos-cate')
        hd_job_category = hd_job_category_elem.text.strip() if hd_job_category_elem else ""

        # 自动提取卡片ID并构造 link
        card_id = card.get('id', '')
        link =""

        job_list.append({
            "announcement_name": announcement_name,
            "publish_time": "",  # 保持原样
            "link": link,  # 自动构造 link
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
