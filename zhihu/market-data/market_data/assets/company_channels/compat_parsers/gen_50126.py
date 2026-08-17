
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for job_card in soup.find_all('a', class_='clearfix'):
        title = job_card.find('div', class_='position-card-title').get('title')
        publish_time = job_card.find('div', class_='position-card-time').text.strip()
        link = job_card.get('href')


        hd_dept =  ''
        hd_loc = ''

        # Assuming hd_job_num and hd_job_category are not provided in the HTML
        hd_job_num = ''
        hd_job_category = ''

        job_list.append({
            "announcement_name": title,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
