
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for job in soup.find_all('a', class_='block flex flex_row_justify'):
        announcement_name = job.find('div', class_='title1').get_text(strip=True) if job.find('div', class_='title1') else ""
        hd_job_category = job.find('div', class_='title2').get_text(strip=True) if job.find('div', class_='title2') else ""
        hd_loc = job.find('div', class_='title3').get_text(strip=True).replace("、",",") if job.find('div', class_='title3') else ""
        publish_time = job.find('div', class_='title4').get_text(strip=True) if job.find('div', class_='title4') else ""
        link = job['href'] if 'href' in job.attrs else ""
        
        job_data = {
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": "",  # Assuming this field is not available in the provided HTML
            "hd_loc": hd_loc,
            "hd_job_num": "",  # Assuming this field is not available in the provided HTML
            "hd_job_category": hd_job_category
        }
        
        job_list.append(job_data)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
