
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    job_elements = soup.find_all('div', class_='link-2tgd22te-3')
    
    for job in job_elements:
        job_info = {}
        link_tag = job.find('a')
        job_info['announcement_name'] = link_tag.find('div', class_='title-20V7ljm-Id').get_text(strip=True).replace("急", "")
        job_info['link'] = link_tag['href']
        job_info['hd_dept'] = ""
        job_info['hd_loc'] = job.find('div', class_='locations-32aEgVWFz_').get_text(strip=True)
        job_info['hd_job_num'] = ''  # Placeholder as the number is not provided in the HTML
        job_info['hd_job_category'] = ''  # Placeholder as the category is not provided in the HTML
        job_info['publish_time'] = ''  # Placeholder as the publish time is not provided in the HTML
        
        job_list.append(job_info)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
