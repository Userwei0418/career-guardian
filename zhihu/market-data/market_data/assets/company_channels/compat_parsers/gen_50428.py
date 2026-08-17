
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    announcements = []

    for a in soup.find_all('a'):
        announcement_name = a.find('span', class_='col-1').text.strip()
        hd_loc = a.find('span', class_='col-2').text.strip()
        hd_job_category = a.find('span', class_='col-3').text.strip()
        hd_job_num = a.find('span', class_='col-4').text.strip()
        publish_time = a.find('span', class_='col-5').text.strip()
        link = a['href']
        hd_dept = ""  # Assuming this field is not available in the provided HTML

        announcements.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": ""
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(announcements, f, ensure_ascii=False, indent=4)
