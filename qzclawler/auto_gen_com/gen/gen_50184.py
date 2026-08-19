
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_items = soup.find_all('div', class_='jobitem')
    
    job_list = []
    
    for job in job_items:
        announcement_name = job.find('div', class_='name').text.strip()
        desc = job.find('div', class_='desc')
        publish_time = ""  # Placeholder as the HTML does not contain this information
        link = ""  # Placeholder as the HTML does not contain this information
        hd_dept = ""  # Placeholder as the HTML does not contain this information
        hd_loc = desc.find('span').text.strip() if desc else ""
        hd_job_num = ""  # Placeholder as the HTML does not contain this information
        hd_job_category = ""  # Placeholder as the HTML does not contain this information
        hd_hopeworktype = ""
        if "实习" in announcement_name:
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
            "hd_hopeworktype": hd_hopeworktype
        })
    
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
