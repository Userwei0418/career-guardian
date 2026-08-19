
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    job_elements = soup.find_all('div', class_='link-2tgd22te-3')
    
    for job in job_elements:
        job_info = {}
        
        title_element = job.find('div', class_='title-20V7ljm-Id')
        job_info['announcement_name'] = title_element.get_text(strip=True) if title_element else ""
        
        link_element = job.find('a')
        job_info['link'] = link_element['href'] if link_element else ""
        
        # Assuming publish_time is not available in the provided HTML
        job_info['publish_time'] = ""
        
        status_element = job.find('div', class_='status-2vTS8JvF_D')
        if status_element:
            spans = status_element.find_all('span', class_='status-item-1_w5ygMyMO')
            job_info['hd_dept'] = spans[0].get_text(strip=True) if len(spans) > 0 else ""
            job_info['hd_job_category'] = spans[1].get_text(strip=True) if len(spans) > 1 else ""
        else:
            job_info['hd_dept'] = ""
            job_info['hd_job_category'] = ""
        if '实习' in job_info['announcement_name']:
            job_info['hd_hopeworktype'] = "实习"
        else:
            job_info['hd_hopeworktype'] = ''
        salary_element = status_element.find('span', class_='salary-HQLh56OSXR') if status_element else None
        job_info['hd_job_num'] = salary_element.get_text(strip=True) if salary_element else ""
        
        location_element = job.find('div', class_='locations-32aEgVWFz_')
        job_info['hd_loc'] = location_element.get_text(strip=True) if location_element else ""
        
        job_list.append(job_info)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
