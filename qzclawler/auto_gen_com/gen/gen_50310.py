
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for job in soup.find_all('div', class_='link-2tgd22te-3'):
        job_info = {}
        link_tag = job.find('a')
        job_info['link'] = link_tag['href']
        
        title_div = job.find('div', class_='title-20V7ljm-Id')
        job_info['announcement_name'] = title_div.get_text(strip=True).replace('急','')
        
        status_div = job.find('div', class_='status-2vTS8JvF_D')
        status_items = status_div.find_all('span', class_='status-item-1_w5ygMyMO')
        job_info['hd_dept'] = status_items[0].get_text(strip=True) if len(status_items) > 0 else ''
        job_info['hd_job_category'] = status_items[1].get_text(strip=True) if len(status_items) > 1 else ''
        
        location_div = job.find('div', class_='locations-32aEgVWFz_')
        job_info['hd_loc'] = location_div.get_text(strip=True) if location_div else ''
        
        publish_time_span = job.find('span', class_='opened-at-20H_gh2Tqd')
        job_info['publish_time'] = publish_time_span.get_text(strip=True).replace('发布时间：', '') if publish_time_span else ''
        
        # Assuming hd_job_num is not provided in the HTML, setting it to a default value
        job_info['hd_job_num'] = '1'  # Default value, as the number is not specified in the HTML
        if "实习" in job_info['announcement_name']:
            job_info['hd_hopeworktype'] = "实习"
        else:
            job_info['hd_hopeworktype'] = ""
        job_list.append(job_info)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
