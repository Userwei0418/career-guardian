
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    job_cards = soup.find_all('div', class_='phw-card-block')

    for job in job_cards:
        title_tag = job.find('h3').find('a')
        announcement_name = title_tag.get_text(strip=True)
        link = title_tag['href']

        job_info = job.find_all('div', class_='_jw-job-info_1ik5l_27')

        hd_dept = hd_loc = hd_job_num = hd_job_category = None

        for info in job_info:
            if 'job-location' in info['data-ph-at-id']:
                hd_loc = info.get_text(strip=True).replace('Location : ', '')
            elif 'job-category' in info['data-ph-at-id']:
                hd_job_category = info.get_text(strip=True).replace('Category : ', '')
            elif 'job-jobId' in info['data-ph-at-id']:
                hd_job_num = info.get_text(strip=True).replace('Job ID : ', '')
            # Assuming hd_dept is not available in the provided HTML structure

        # Assuming publish_time is not available in the provided HTML structure
        publish_time = None

        job_list.append({
            "announcement_name": announcement_name,
            "publish_time": "",
            "link": link,
            "hd_dept": "",
            "hd_loc": "",
            "hd_job_num": "",
            "hd_job_category": ""
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
