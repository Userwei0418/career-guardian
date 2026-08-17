
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for tr in soup.find_all('div', class_='tr'):
        announcement_name = tr.find('div', class_='td name').get('title', '')
        publish_time = tr.find('div', class_='td date').get('title', '')
        link = tr.find('div', class_='td name').a['href'] if tr.find('div', class_='td name').a else ''
        hd_dept = tr.find('div', class_='td group').get('title', '')
        hd_loc = tr.find('div', class_='td place').get('label', '')
        hd_job_num = ''  # No information provided in the HTML
        hd_job_category = tr.find('div', class_='td category').get('title', '')

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
