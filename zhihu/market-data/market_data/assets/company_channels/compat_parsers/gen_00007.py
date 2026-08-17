
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    positions = []

    for position in soup.find_all('a', class_='positionLists'):
        announcement_name = position.find('div', class_='positionName').get('title')
        publish_time = position.find('span', text=lambda x: x and '发布时间' in x).text.split('：')[1].strip()
        link = position.get('href')
        hd_dept = position.find_all('span')[0].text
        hd_category = position.find_all('span')[1].text
        hd_loc = position.find_all('span')[2].text
        hd_job_num = position.find('span', text=lambda x: x and '招聘人数' in x).text.split('：')[1].strip()

        positions.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_category
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(positions, f, ensure_ascii=False, indent=4)