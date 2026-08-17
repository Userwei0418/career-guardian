
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for card in soup.find_all('div', class_='card-item-wrap'):
        announcement_name = card.find('div', class_='pos-title-item').get('title', '') if card.find('div', class_='pos-title-item') else ""
        publish_time = card.find('span', class_='pub-time').text.replace('更新日期：', '') if card.find('span', class_='pub-time') else ""
        link = ""  # Assuming no link is provided in the HTML
        hd_dept = card.find('div', class_='pos-summary').find_all('span')[0].text if card.find('div', class_='pos-summary') else ""
        hd_loc = card.find('div', class_='pos-summary').find_all('span')[1].text.replace("、",",") if len(card.find('div', class_='pos-summary').find_all('span')) > 1 else ""
        hd_job_num = ""  # Assuming no job number is provided in the HTML
        hd_job_category = card.find('span', class_='pos-cate').get('title', '') if card.find('span', class_='pos-cate') else ""

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
