
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    job_elements = soup.find_all('a', class_='block p-3 mb-5 rounded-lg hover:bg-fill-hover')

    for job in job_elements:
        announcement_name = job.find('div', class_='text-title text-h4 mb-2 font-medium').get_text(strip=True) if job.find('div', class_='text-title text-h4 mb-2 font-medium') else ""
        link = job['href'] if 'href' in job.attrs else ""
        publish_time = ""  # Placeholder as the HTML does not contain this information
        hd_dept = ""  # Placeholder as the HTML does not contain this information
        hd_loc = job.find_all('span')[3].get_text(strip=True) if job.find_all('span') else ""
        hd_job_num = ""  # Placeholder as the HTML does not contain this information
        hd_job_category = job.find('span', class_='i-icon i-icon-handbag mr-2').get_text(strip=True) if job.find('span', class_='i-icon i-icon-handbag mr-2') else ""
        if '实习' in announcement_name:
            hd_hopeworktype = "实习"
        else:
            hd_hopeworktype = ""
        job_list.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category,
            "hd_hopeworktype":hd_hopeworktype
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
