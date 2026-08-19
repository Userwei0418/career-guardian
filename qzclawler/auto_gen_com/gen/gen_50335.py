
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    announcements = []

    # Extracting the announcement details
    for li in soup.find_all('li'):
        link = li.find('a')
        if link:
            announcement_name = link.get('title')
            link_url = link.get('href')
            # Placeholder values for other fields as they are not present in the provided HTML
            publish_time = ""
            hd_dept = ""
            hd_loc = ""
            hd_job_num = ""
            hd_job_category = ""
            
            announcement = {
                "announcement_name": announcement_name,
                "publish_time": publish_time,
                "link": link_url,
                "hd_dept": hd_dept,
                "hd_loc": hd_loc,
                "hd_job_num": hd_job_num,
                "hd_job_category": hd_job_category
            }
            announcements.append(announcement)

    # Writing the extracted data to a JSON file
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(announcements, f, ensure_ascii=False, indent=4)
