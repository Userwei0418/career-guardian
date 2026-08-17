
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    job_elements = soup.find_all('div', class_='link-2tgd22te-3')

    for job in job_elements:
        title = job.find('div', class_='title-20V7ljm-Id').get_text(strip=True)
        link = job.find('a')['href']
        status_items = job.find('div', class_='status-2vTS8JvF_D').find_all('span', class_='status-item-1_w5ygMyMO')

        announcement_name = title
        publish_time = ""  # Assuming there's no publish time in the provided HTML
        hd_dept = status_items[0].get_text(strip=True) if len(status_items) > 0 else ""
        hd_job_category = status_items[1].get_text(strip=True) if len(status_items) > 1 else ""
        hd_loc = job.find('div', class_='locations-32aEgVWFz_').get_text(strip=True) if job.find('div', class_='locations-32aEgVWFz_') else ""
        hd_job_num = ""  # Assuming there's no job number in the provided HTML

        job_info = {
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        }

        job_list.append(job_info)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
