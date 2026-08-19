
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for li in soup.find_all('li'):
        announcement_name = li.find('b').get_text(strip=True) if li.find('b') else ""
        publish_time = li.find('i', class_='dateshow').get_text(strip=True) if li.find('i', class_='dateshow') else ""
        link = li.find('a', class_='more')['href'] if li.find('a', class_='more') else ""
        hd_dept = ""  # No data available in the provided HTML
        hd_loc = li.find('ol').find_all('i')[1].get_text(strip=True) if li.find('ol') else ""
        hd_job_num = ""  # No data available in the provided HTML
        hd_job_category = ""  # No data available in the provided HTML

        job_list.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": "",
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
