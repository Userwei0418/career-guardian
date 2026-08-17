
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for card in soup.find_all('div', class_='list-card-item1'):
        announcement_name = card.find('span', class_='top-label').text.strip()
        hd_dept = card.find_all('span')[0].text.strip()  # Assuming the first span is the department
        hd_loc = card.find('span', class_='work-place').text.strip().replace('|','')
        hd_job_num = card.find('span', class_='need-people').text.replace('招聘人数：', '').strip()
        hd_job_category = card.find('span', class_='pos-cate').text.strip()

        job_info = {
            "announcement_name": announcement_name,
            "publish_time": "",  # Assuming no publish time is provided in the HTML
            "link": "",  # Assuming no link is provided in the HTML
            "hd_dept": "",
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        }

        job_list.append(job_info)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
