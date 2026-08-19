
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for job_card in soup.find_all('div', class_='container-aOp138AX_X'):
        job_info = {}
        link = job_card.find('a', class_='link-txmgVOCVz9')
        job_info['link'] = link['href'] if link else None
        
        title = job_card.find('span', class_='title-u2qk9xX9Ie')
        job_info['announcement_name'] = title.get_text(strip=True) if title else None
        
        company = job_card.find('div', class_='sd-Ellipsis-hiddenContent-1Skwh')
        job_info['hd_dept'] = company.get_text(strip=True) if company else None
        
        job_type = job_card.find_all('div', class_='sd-foundation-body-secondary-1Z7H-')
        job_info['hd_job_category'] = job_type[1].get_text(strip=True) if len(job_type) > 1 else None
        
        location = job_type[2].get_text(strip=True) if len(job_type) > 2 else None
        job_info['hd_loc'] = location
        
        job_info['hd_job_num'] = ""  # Placeholder as the number of positions is not provided in the HTML
        
        # Assuming publish_time is not available in the provided HTML
        job_info['publish_time'] = ""
        
        job_list.append(job_info)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
