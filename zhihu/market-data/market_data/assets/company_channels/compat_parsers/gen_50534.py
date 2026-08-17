
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for li in soup.find_all('li'):
        announcement_name = li.find('div', class_='column-1').get_text(strip=True) if li.find('div', class_='column-1') else ""
        publish_time = ""  # Assuming there's no publish time in the provided HTML
        link = li.find('a', class_='scan')['href'] if li.find('a', class_='scan') else ""
        hd_dept = li.find('div', class_='column-3').get_text(strip=True) if li.find('div', class_='column-3') else ""
        hd_loc = li.find('div', class_='column-2').get_text(strip=True) if li.find('div', class_='column-2') else ""
        hd_job_num = li.find('div', class_='column-5').get_text(strip=True) if li.find('div', class_='column-5') else ""
        hd_job_category =  ""

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
