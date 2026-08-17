
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    post_list = soup.find('div', id='postList')
    for job in post_list.find_all('ul', class_='overhidden c333 mt20 lh24'):
        job_details = {}
        job_items = job.find_all('li')

        job_details['announcement_name'] = job_items[0].find('span').get('title')
        job_details['hd_dept'] = job_items[1].get('title')
        job_details['hd_loc'] = job_items[2].get('title')
        job_details['publish_time'] = job_items[3].text.strip()
        job_details['link'] = ""

        # Placeholder for hd_job_num and hd_job_category as they are not present in the provided HTML
        job_details['hd_job_num'] = ""
        job_details['hd_job_category'] = ""

        job_list.append(job_details)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
