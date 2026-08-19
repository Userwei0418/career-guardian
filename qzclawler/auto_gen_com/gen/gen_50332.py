
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    announcements = []

    for li in soup.find_all('li'):
        time_div = li.find('div', class_='time')
        title_div = li.find('div', class_='title')
        if time_div and title_div:
            announcement_name = title_div.a.text
            publish_time = time_div.text
            link = title_div.a['href']
            # Placeholder values for the other fields
            hd_dept = ""
            hd_loc = ""
            hd_job_num = ""
            hd_job_category = ""

            announcement = {
                "announcement_name": announcement_name,
                "publish_time": publish_time,
                "link": link,
                "hd_dept": hd_dept,
                "hd_loc": hd_loc,
                "hd_job_num": hd_job_num,
                "hd_job_category": hd_job_category
            }
            announcements.append(announcement)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(announcements, f, ensure_ascii=False, indent=4)
