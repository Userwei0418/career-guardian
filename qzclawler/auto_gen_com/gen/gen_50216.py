
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    announcements = []

    for item in soup.find_all("div", class_="_2AOmjKmlEtuR_KEoehWYcN"):
        announcement_name = item.find("div", class_="_1RRlPtjyYmeDGCWt9lrk2P").text.strip()
        publish_time = item.find("div", class_="_3Jn5Z6PZA5H7Auzy0xlXu2").text.replace("更新于 ", "").strip()
        hd_dept = item.find("div", class_="_1KYNSENqWg4IDHby5E9sqK").text.strip()
        hd_loc = item.find_all("div", class_="_3CJNtKfv5mLnNfeqL1jgRB")[0].text.strip()
        hd_job_num = ""  # Assuming job number is not provided in the HTML
        hd_job_category = hd_dept.split('-')[0] if '-' in hd_dept else "不详"  # Extracting category from department

        announcement = {
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": "",  # Assuming no link is provided in the HTML
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        }
        announcements.append(announcement)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(announcements, f, ensure_ascii=False, indent=4)
