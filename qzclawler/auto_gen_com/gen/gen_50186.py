
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    positions = []

    for item in soup.find_all('div', class_='position-item'):
        announcement_name = item.find('div', class_='item-name').get('title', '')
        publish_time = item.find('div', class_='item-time').text.strip()
        link = ''  # Assuming no link is provided in the HTML
        hd_dept = ''  # Assuming no department info is provided in the HTML
        hd_loc = item.find('div', class_='item-location').get('title', '')
        hd_job_num = ''  # Assuming no job number info is provided in the HTML
        hd_job_category = item.find('div', class_='item-type').get('title', '')

        position = {
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        }
        positions.append(position)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(positions, f, ensure_ascii=False, indent=4)
