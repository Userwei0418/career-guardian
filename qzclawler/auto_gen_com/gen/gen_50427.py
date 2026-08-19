
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_listings = []

    for job in soup.find_all(class_='j-item'):
        job_name = job.find(class_='job-name').get_text(strip=True)
        job_type = job.find(class_='job-type').get_text(strip=True).split('｜')
        publish_time = ""  # Placeholder as the publish time is not provided in the HTML
        link = job.find(class_='share-link').find('span').get_text(strip=True)
        hd_dept = job_type[0] if len(job_type) > 0 else ""
        hd_loc = job_type[2] if len(job_type) > 2 else ""
        hd_job_num = ""  # Placeholder as the job number is not provided in the HTML
        hd_job_category = job_type[1].replace(" ","") if len(job_type) > 1 else ""

        job_listings.append({
            "announcement_name": job_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": "",
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_listings, f, ensure_ascii=False, indent=4)
