
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    announcements = soup.find_all('div', class_='jwPAC7jgWIKUro5l4bE3')
    
    for announcement in announcements:
        title = announcement.find('div', class_='_2FC_nJGFTgU6s7ZTaFvuL8 _3vj2eS7k7Mwpko5_6OSRu2').text.strip()
        publish_time = announcement.find('div', class_='oAdZgV3YZC3NawYz0Ocyy').text.replace('更新于 ', '').strip()
        job_category = announcement.find('div', class_='_3JJTjjGoQPkS4t1NWmlpAM').text.strip()
        location = announcement.find('div', class_='O2l16_NlF-uGFa5WEZRHY').text.strip().replace('/',',')
        
        job_info = {
            "announcement_name": title,
            "publish_time": publish_time,
            "link": "",  # Link is not provided in the HTML snippet
            "hd_dept": "",  # Department is not provided in the HTML snippet
            "hd_loc": location,
            "hd_job_num": "",  # Job number is not provided in the HTML snippet
            "hd_job_category": job_category
        }
        
        job_list.append(job_info)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
