
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for item in soup.find_all('a', class_='result_item'):
        announcement_name = item.find('div', class_='div1').get_text(strip=True)
        publish_time = ""  # Assuming publish_time is not available in the provided HTML
        link = item['href']
        hd_dept = ""  # Assuming hd_dept is not available in the provided HTML
        hd_loc = item.find('div', class_='div3').find('span').get_text(strip=True)
        hd_job_num = ""  # Assuming hd_job_num is not available in the provided HTML
        text = item.find('div', class_='div2').get_text(strip=True)
        hd_job_category = text.split('丨')[0].strip()
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
