
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for job in soup.find_all('div', class_='link-2tgd22te-3'):
        job_info = {}
        
        # Extract link
        link_tag = job.find('a')
        job_info['link'] = link_tag['href'] if link_tag else ""
        
        # Extract announcement name
        title_div = job.find('div', class_='title-20V7ljm-Id')
        job_info['announcement_name'] = title_div.get_text(strip=True).replace("急","") if title_div else ""
        
        # Extract publish time
        publish_time_span = job.find('span', class_='opened-at-20H_gh2Tqd')
        job_info['publish_time'] = publish_time_span.get_text(strip=True).replace("发布时间：", "") if publish_time_span else ""
        
        # Extract department or institution
        job_info['hd_dept'] = job_info['announcement_name'].split('—')[1] if '—' in job_info['announcement_name'] else ""
        
        # Extract work location
        locations_div = job.find('div', class_='locations-32aEgVWFz_')
        job_info['hd_loc'] =  ""
        
        # Extract job number (not available in the provided HTML, so set to "")
        job_info['hd_job_num'] = ""
        
        # Extract job category (not available in the provided HTML, so set to "")
        job_info['hd_job_category'] = ""
        job_info['hd_hopeworktype'] = "实习" if "实习" in job_info['announcement_name'] else ""

            

        job_list.append(job_info)

    # Write to JSON file
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
