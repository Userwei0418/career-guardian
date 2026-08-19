
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for card in soup.find_all('div', class_='list-card-item1'):
        announcement_name = card.find('span', class_='top-label').get_text(strip=True) if card.find('span', class_='top-label') else ""
        publish_time = card.find('span', class_='pub-time').get_text(strip=True).replace("更新日期：", "") if card.find('span', class_='pub-time') else ""
        link = ""  # Assuming no link is provided in the HTML
        hd_dept = ""
        hd_loc = card.find('span', class_='work-place').get_text(strip=True).replace("|",'') if card.find('span', class_='work-place') else ""
        hd_job_num = card.find('span', class_='need-people').get_text(strip=True).replace("招聘人数：", "") if card.find('span', class_='need-people') else ""
        hd_job_category = ""  # Assuming no job category is provided in the HTML

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
