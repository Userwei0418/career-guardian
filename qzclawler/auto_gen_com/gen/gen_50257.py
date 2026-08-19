import json
import re
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for job in soup.find_all('div', class_=re.compile('^link-')):
        job_info = {}
        link_tag = job.find('a')

        title_div = link_tag.find('div', class_=re.compile('^title-')) if link_tag else None
        job_info['announcement_name'] = title_div.text.strip() if title_div else ''

        job_info['link'] = link_tag['href'] if link_tag and 'href' in link_tag.attrs else ''

        status_div = link_tag.find('div', class_=re.compile('^status-')) if link_tag else None
        if status_div:
            spans = status_div.find_all('span')
            job_info['hd_job_category'] = spans[1].text.strip() if len(spans) > 1 else ''
        else:
            job_info['hd_job_category'] = ''

        location_div = link_tag.find('div', class_=re.compile('^locations-')) if link_tag else None
        job_info['hd_loc'] = ''

        job_info['hd_dept'] = ''
        job_info['hd_job_num'] = ''
        job_info['publish_time'] = ''

        job_list.append(job_info)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
