
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    job_elements = soup.find_all('div', class_='link-2tgd22te-3')

    for job in job_elements:
        announcement_name = job.find('div', class_='title-20V7ljm-Id').get_text(strip=True).replace("急","") if job.find('div', class_='title-20V7ljm-Id') else ""
        publish_time = job.find('span', class_='opened-at-20H_gh2Tqd').get_text(strip=True).replace("发布时间：", "") if job.find('span', class_='opened-at-20H_gh2Tqd') else ""
        link = job.find('a')['href'] if job.find('a') else ""
        hd_dept = job.find_all('span', class_='status-item-1_w5ygMyMO')[0].get_text(strip=True) if job.find_all('span', class_='status-item-1_w5ygMyMO') else ""
        hd_job_category = job.find_all('span', class_='status-item-1_w5ygMyMO')[1].get_text(strip=True) if len(job.find_all('span', class_='status-item-1_w5ygMyMO')) > 1 else ""
        hd_loc = job.find('div', class_='locations-32aEgVWFz_').get_text(strip=True) if job.find('div', class_='locations-32aEgVWFz_') else ""
        hd_job_num = ""  # Assuming this field is not available in the provided HTML

        job_list.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
