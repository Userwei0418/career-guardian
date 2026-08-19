
import json
from urllib.parse import urlencode

from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_data = []

    rows = soup.select('tbody#jobData tr')
    for row in rows:
        cols = row.find_all('td')
        if len(cols) >= 5:
            announcement_name = cols[1].get_text(strip=True)
            hd_dept = cols[0].get_text(strip=True)
            hd_loc = cols[2].get_text(strip=True)
            hd_job_num = cols[3].get_text(strip=True)
            publish_time = cols[4].get_text(strip=True)
            jobId = row['onclick'].split('(')[1].split(',')[0].strip("'").strip()
            parmes = { 'type' : 1}
            token = {'csrftoken' : '508211516408593193'}
            link =f"jobDetail?jobId={jobId}&{urlencode(parmes)}&{urlencode(token)}" # Extract job ID from onclick

            job_data.append({
                "announcement_name": announcement_name,
                "publish_time": publish_time,
                "link": link,
                "hd_dept": hd_dept,
                "hd_loc": hd_loc,
                "hd_job_num": hd_job_num,
                "hd_job_category": ""  # Placeholder for job category, as it's not provided in the HTML
            })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_data, f, ensure_ascii=False, indent=4)
