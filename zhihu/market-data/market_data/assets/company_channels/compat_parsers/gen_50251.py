import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for card in soup.find_all('div', class_='list-card-item1'):
        title = card.find('span', class_='top-label').get_text(strip=True) if card.find('span', class_='top-label') else ""
        company_tag = card.find('span', class_='split').find_previous_sibling() if card.find('span', class_='split') else None
        company = company_tag.get_text(strip=True) if company_tag else ""
        work_type = card.find('span', class_='work-type').get_text(strip=True) if card.find('span', class_='work-type') else ""
        work_place = card.find('span', class_='work-place').get_text(strip=True).replace('|', '') if card.find('span', class_='work-place') else ""

        # ✅ 精确提取发布时间
        pub_time_tag = card.find('span', class_='pub-time')
        if pub_time_tag:
            pub_time = pub_time_tag.get_text(strip=True).replace('发布时间：', '')
        else:
            pub_time = ''

        job_info = {
            "announcement_name": title,
            "publish_time": pub_time,
            "link": "",
            "hd_dept": company,
            "hd_loc": work_place,
            "hd_job_num": "",
            "hd_job_category": work_type
        }

        job_list.append(job_info)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
