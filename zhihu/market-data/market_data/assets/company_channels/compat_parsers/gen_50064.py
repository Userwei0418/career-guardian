
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    job_elements = soup.find_all('div', class_='link-2tgd22te-3')

    for job in job_elements:
        job_info = {}
        link_tag = job.find('a')
        job_info['link'] = link_tag['href']

        title_div = job.find('div', class_='title-20V7ljm-Id')
        job_info['announcement_name'] = title_div.get_text(strip=True)

        status_div = job.find('div', class_='status-2vTS8JvF_D')
        status_items = status_div.find_all('span', class_='status-item-1_w5ygMyMO')

        job_info['hd_dept'] = status_items[0].get_text(strip=True) if len(status_items) > 0 else ''
        job_info['hd_job_category'] = status_items[2].get_text(strip=True) if len(status_items) > 2 else ''

        location_div = job.find('div', class_='locations-32aEgVWFz_')
        job_info['hd_loc'] = location_div.get_text(strip=True) if location_div else ''

        job_info['hd_job_num'] = ''  # Assuming this field is not available in the provided HTML

        publish_time_span = job.find('span', class_='opened-at-20H_gh2Tqd')
        job_info['publish_time'] = publish_time_span.get_text(strip=True).replace('发布时间：', '') if publish_time_span else ''

        job_list.append(job_info)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
