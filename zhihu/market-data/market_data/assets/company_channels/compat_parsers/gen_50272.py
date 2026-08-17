
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for job in soup.find_all('div', class_='content_wrap_list'):
        link_tag = job.find('a')
        announcement_name = job.find('h1').text.strip()
        publish_time = job.find('p', class_='date').text.strip()
        link = link_tag['href']

        details = job.find('ul').find_all('li')
        hd_dept = details[0].find('span').text.strip()
        hd_loc = details[1].find('span').text.strip()
        hd_job_num = details[2].find('span').get('title', details[2].find('span').text.strip())
        hd_job_category = ''  # Assuming this field is not available in the provided HTML

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
