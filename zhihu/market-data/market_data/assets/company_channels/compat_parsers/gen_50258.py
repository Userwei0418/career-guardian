
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    announcements = []

    # Extracting announcement details
    for p in soup.find_all('p'):
        announcement_name = p.get_text(strip=True)
        # Placeholder values for other fields as they are not provided in the HTML
        publish_time = ""
        link = ""
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

    # Writing to JSON file
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(announcements, f, ensure_ascii=False, indent=4)
