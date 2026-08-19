
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    job_elements = soup.find_all('div', class_='link-2tgd22te-3')
    
    for job in job_elements:
        job_info = {}
        
        # Extracting announcement name
        title_div = job.find('div', class_='title-20V7ljm-Id')
        job_info['announcement_name'] = title_div.get_text(strip=True).replace("急","") if title_div else ""
        
        # Extracting publish time
        publish_time_span = job.find('span', class_='opened-at-20H_gh2Tqd')
        job_info['publish_time'] = publish_time_span.get_text(strip=True).replace("发布时间：", "") if publish_time_span else ""
        
        # Extracting link
        link_tag = job.find('a')
        job_info['link'] = link_tag['href'] if link_tag else ""
        
        # Extracting department or institution
        job_info['hd_dept'] = ""  # No specific field in the provided HTML
        
        # Extracting work location
        location_div = job.find('div', class_='locations-32aEgVWFz_')
        job_info['hd_loc'] = location_div.get_text(strip=True) if location_div else ""
        
        # Extracting number of recruits
        job_info['hd_job_num'] = ""  # No specific field in the provided HTML
        
        # Extracting job category
        status_div = job.find('div', class_='status-2vTS8JvF_D')
        job_categories = status_div.find_all('span', class_='status-item-1_w5ygMyMO') if status_div else []
        job_info['hd_job_category'] = ", ".join([cat.get_text(strip=True) for cat in job_categories]) if job_categories else ""
        if '实习' in job_info['announcement_name']:
            job_info['hd_hopeworktype'] = "实习"
        else:
            job_info['hd_hopeworktype'] = ""
        job_list.append(job_info)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
