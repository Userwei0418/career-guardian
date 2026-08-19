
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for a_tag in soup.find_all('a'):
        job_info = {}
        job_details = a_tag.find('ul')

        if job_details:
            job_info['announcement_name'] = job_details.find('li', class_='one').get_text(strip=True) if job_details.find('li', class_='one') else ""
            job_info['publish_time'] = ""  # No publish time in the provided HTML
            job_info['link'] = a_tag['href'] if 'href' in a_tag.attrs else ""
            job_info['hd_dept'] = ""  # No department info in the provided HTML
            job_info['hd_loc'] = ""  # No location info in the provided HTML
            job_info['hd_job_num'] = ""  # No job number info in the provided HTML
            job_info['hd_job_category'] = job_details.find('li', class_='zero').get_text(strip=True) if job_details.find('li', class_='zero') else ""

        job_list.append(job_info)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
