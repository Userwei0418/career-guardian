
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for job_div in soup.find_all('div', style=lambda value: value and 'width: 1200px' in value):
        announcement_name = job_div.find('div', style=lambda value: value and 'font-size: 22px' in value).get_text(strip=True)
        link = job_div.find('a')['href']
        publish_time = job_div.find_all('div', style=lambda value: value and 'font-size: 16px' in value)[0].get_text(strip=True).split(' | ')[-1]
        hd_dept = ""  # Assuming this is a constant value based on the provided HTML
        hd_loc = job_div.find_all('span')[1].get_text(strip=True)
        hd_job_num = ""  # Assuming this is a constant value based on the provided HTML
        hd_job_category = ""  # Assuming this is a constant value based on the provided HTML

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
