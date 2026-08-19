
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for li in soup.select('ul > li:not(.tit)'):
        a_tag = li.find('a')
        announcement_name = a_tag.find('div', class_='zp_position').get_text(strip=True)
        publish_time = a_tag.find('div', class_='zp_time').get_text(strip=True)
        link = a_tag['href']
        hd_dept = a_tag.find('div', class_='zp_class').get_text(strip=True)
        hd_loc = a_tag.find('div', class_='zp_dd').get_text(strip=True)
        hd_job_num = a_tag.find('div', class_='zp_rs').get_text(strip=True)
        hd_job_category = ''  # Assuming this field is not available in the provided HTML

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
