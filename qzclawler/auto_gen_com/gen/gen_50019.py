import json
from bs4 import BeautifulSoup


def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for card in soup.find_all('div', class_='list-card-item1'):
        # 职位名称
        announcement_name = card.find('span', class_='top-label').text.strip() if card.find('span',
                                                                                            class_='top-label') else ''

        # 发布时间
        publish_time = card.find('span', class_='pub-time').text.replace('发布时间：', '').strip() if card.find('span',
                                                                                                               class_='pub-time') else ''

        # 链接：直接用 div 的 id 构造 postId
        post_id = card.get('id', '')
        link = ""

        # 部门（公司名）
        hd_dept_span = card.find('div', class_='pos-summary').find_all('span')[0] if card.find('div',
                                                                                               class_='pos-summary') else ''
        hd_dept = hd_dept_span.text.replace('|', '').strip() if hd_dept_span else ''

        # 地点
        hd_loc = card.find('span', class_='work-place').text.strip().replace('|', '') if card.find('span', class_='work-place') else ''

        # 招聘人数
        hd_job_num = card.find('span', class_='need-people').text.replace('招聘人数：', '').strip() if card.find('span',
                                                                                                                class_='need-people') else ''

        # 职位类别
        hd_job_category = card.find('span', class_='pos-cate').text.strip() if card.find('span',
                                                                                         class_='pos-cate') else ''

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
