import json
from bs4 import BeautifulSoup


def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    announcements = []

    for item in soup.select('.list-group-item'):
        announcement_name = item.h3.a.get('title', '') if item.h3.a else ""
        link = item.h3.a.get('href', '') if item.h3.a else ""
        hd_dept = item.find('h5').get('title', '') if item.find('h5') else ""
        hd_loc = ""
        hd_job_num = ""
        hd_job_category = ""

        # Extract location and job number
        for li in item.select('.list-inline li'):
            text = li.get_text(strip=True)
            if "招聘人数：" in text:
                hd_job_num = text.replace("招聘人数：", "")
            else:
                hd_loc = text

        # Create the announcement dictionary
        announcement = {
            "announcement_name": announcement_name,
            "publish_time": "",  # No publish time in the provided HTML
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        }

        announcements.append(announcement)

    # Write to JSON file
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(announcements, f, ensure_ascii=False, indent=4)


