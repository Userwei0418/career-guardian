
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    recruitment_items = soup.find_all('div', class_='recruitment_position_list_item')

    result = []

    for item in recruitment_items:
        announcement_name = item.find('span', class_='recrupos_area').text.strip()
        publish_time = ""
        hd_dept = item.find('div', class_='recrupos_detail_info').text.strip().split('|')[1].strip()
        hd_loc = item.find('div', class_='recrupos_city').find('span').text.strip()
        hd_job_num = item.find('div', class_='recrupos_detail_info').text.strip().split('|')[-1].strip()
        hd_job_category = ""

        result.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": "",  # Assuming no link is provided in the HTML
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=4)
