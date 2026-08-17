
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for card in soup.find_all('div', class_='card-item-wrap'):
        announcement_name = card.find('span', class_='top-label').get_text(strip=True) if card.find('span', class_='top-label') else ""
        publish_time = card.find('span', class_='pub-time').get_text(strip=True).replace("发布时间：", "") if card.find('span', class_='pub-time') else ""
        link = ""  # Assuming link extraction is not specified in the provided HTML
        hd_dept = card.find('div', class_='pos-summary').get_text(strip=True).split('|')[0] if card.find('div', class_='pos-summary') else ""
        hd_loc = card.find('span', class_='work-place').get_text(strip=True).replace("|","") if card.find('span', class_='work-place') else ""
        hd_job_num = ""  # Not provided in the HTML
        hd_job_category = ""  # Not provided in the HTML

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
