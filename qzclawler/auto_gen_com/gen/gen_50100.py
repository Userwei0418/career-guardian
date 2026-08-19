
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for li in soup.find_all('li'):
        job_info = {}
        link_tag = li.find('a', class_='search-results-link')
        
        if link_tag:
            job_info['announcement_name'] = link_tag.h2.text.strip()
            job_info['link'] = link_tag['href']
            job_info['hd_loc'] = link_tag.find('span', class_='job-location').text.strip()
            job_info['hd_dept'] = ""  # Placeholder as the department is not provided in the HTML
            job_info['hd_job_num'] = ""  # Placeholder as the job number is not provided in the HTML
            job_info['hd_job_category'] = ""  # Placeholder as the job category is not provided in the HTML
            job_info['publish_time'] = ""  # Placeholder as the publish time is not provided in the HTML
            
            job_list.append(job_info)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
