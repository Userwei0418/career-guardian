
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for card in soup.find_all('div', class_='card-item-wrap'):
        announcement_name = card.find('div', class_='pos-title-item').get('title', '')
        publish_time = card.find('span', class_='pub-time').text.replace('发布时间：', '').strip() if card.find('span', class_='pub-time') else ""
        hd_job_num = card.find('span', class_='need-people').text.replace('招聘人数：', '').strip() if card.find('span', class_='need-people') else ""
        hd_dept =  ""
        hd_loc = card.find('div', class_='pos-summary').get('title', '').split('|')[-1].strip() if card.find('div', class_='pos-summary') else ""
        hd_job_category = card.find('span', class_='pos-cate').get('title', '') if card.find('span', class_='pos-cate') else ""
        link = ""  # Assuming link is not provided in the HTML context

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
