import json
from bs4 import BeautifulSoup


def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for li in soup.find_all('li'):
        job_info = {}
        a_tag = li.find('a')
        job_info['announcement_name'] = a_tag.find('dd', class_='dd01').em.text
        job_info['link'] = a_tag['href']
        job_info['hd_job_num'] = a_tag.find('dd', class_='dd02').text
        job_info['publish_time'] = a_tag.find('dd', class_='dd03').text
        job_info['hd_dept'] = ''  # Placeholder, as the data is not provided in the HTML
        job_info['hd_loc'] = ''  # Placeholder, as the data is not provided in the HTML
        job_info['hd_job_category'] = ''  # Placeholder, as the data is not provided in the HTML

        job_list.append(job_info)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
