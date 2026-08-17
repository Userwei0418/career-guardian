
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    job_elements = soup.find_all('div', class_='jwPAC7jgWIKUro5l4bE3')

    for job in job_elements:
        announcement_name = job.find('div', class_='_2FC_nJGFTgU6s7ZTaFvuL8 _3vj2eS7k7Mwpko5_6OSRu2').text.strip()
        publish_time = job.find('div', class_='oAdZgV3YZC3NawYz0Ocyy').text.replace('更新于 ', '').strip()
        hd_dept = ""  # Placeholder as the department is not provided in the HTML
        hd_loc = job.find('div', class_='O2l16_NlF-uGFa5WEZRHY').text.strip().replace('/',',')
        hd_job_num = "1"  # Placeholder as the job number is not provided in the HTML
        hd_job_category = job.find('div', class_='_3JJTjjGoQPkS4t1NWmlpAM').text.strip()
        link = ""  # Placeholder as the link is not provided in the HTML

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
