
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for li in soup.find_all('li')[1:]:  # Skip the first li which is the header
        job_info = {}
        link_tag = li.find('a')
        if link_tag:
            job_info['announcement_name'] = link_tag.find('div', class_='item-left').text.strip() if link_tag.find('div', class_='item-left') else ""
            job_info['link'] = link_tag['href'] if 'href' in link_tag.attrs else ""
            job_info['hd_loc'] = link_tag.find('div', class_='item-right').text.strip() if link_tag.find('div', class_='item-right') else ""
        else:
            job_info['announcement_name'] = ""
            job_info['link'] = ""
            job_info['hd_loc'] = ""

        # Assigning empty strings for the other fields as they are not present in the HTML
        job_info['publish_time'] = ""
        job_info['hd_dept'] = ""
        job_info['hd_job_num'] = ""
        job_info['hd_job_category'] = ""

        job_list.append(job_info)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
