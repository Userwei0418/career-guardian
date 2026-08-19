
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    rows = soup.select('table.jobsTable tbody tr')[1:]  # Skip the header row
    for row in rows:
        cols = row.find_all('td')
        if len(cols) < 4:
            continue

        announcement_name = cols[0].get_text(strip=True)
        link = cols[0].a['href'] if cols[0].a else ""
        publish_time = cols[-1].get_text(strip=True)
        hd_dept = ""
        hd_loc = ""
        hd_job_num = ""  # Not provided in the HTML
        hd_job_category =""
        if "实习" in announcement_name:
            hd_hopeworktype = "实习"
        else:
            hd_hopeworktype = ""
        job_list.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category,
            "hd_hopeworktype": hd_hopeworktype
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
