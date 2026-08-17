
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_ads = soup.find_all('li', class_='job_ad_list')

    result = []

    for job in job_ads:
        announcement_name = job.find_all('span')[0].get_text(strip=True)
        hd_dept = ""
        hd_loc = job.find_all('span')[2].get_text(strip=True)
        publish_time = job.find_all('span')[3].get_text(strip=True)
        link = job.find('a')['href'] if job.find('a') else ""
        hd_job_num = ""  # Assuming this field is not available in the provided HTML
        hd_job_category = job.find_all('span')[1].get_text(strip=True)  # Assuming this field is not available in the provided HTML

        result.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=4)
