import json
from bs4 import BeautifulSoup


def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    job_cards = soup.find_all('div', class_='rocket-card-body')

    for card in job_cards:
        # 安全获取标题和链接
        title_elem = card.find('a', class_='font-28')
        announcement_name = title_elem.text.strip() if title_elem else ''

        link_elem = card.find('a', class_='recruit-link')
        link = link_elem['href'] if link_elem and link_elem.has_attr('href') else ''

        # 安全获取各字段
        publish_elem = card.find('span', class_='detail-pos-text', text=lambda x: x and '202' in x)
        publish_time = publish_elem.text.strip() if publish_elem else ''

        dept_elem = card.find('span', class_='detail-pos-text', text=lambda x: x and '类' in x)
        hd_dept = dept_elem.text.strip() if dept_elem else ''

        spans = card.find_all('span', class_='detail-pos-text')
        hd_loc = spans[1].text.strip() if len(spans) > 1 else ''
        hd_job_num = spans[2].text.strip() if len(spans) > 2 else ''
        hd_job_category = spans[3].text.strip() if len(spans) > 3 else ''

        job_list.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": ""
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
