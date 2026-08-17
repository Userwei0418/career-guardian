
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    table_rows = soup.select('table.jobsTable tbody tr')

    job_list = []

    for row in table_rows[1:]:  # Skip the header row
        cols = row.find_all('td')
        if len(cols) < 4:
            continue

        announcement_name = cols[0].get_text(strip=True)
        link = cols[0].a['href'] if cols[0].a else ""
        hd_dept = ""  # No corresponding data in the provided HTML
        hd_loc = ""
        publish_time = cols[3].get_text(strip=True)
        hd_job_num = ""  # No corresponding data in the provided HTML
        hd_job_category = cols[1].get_text(strip=True)

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
