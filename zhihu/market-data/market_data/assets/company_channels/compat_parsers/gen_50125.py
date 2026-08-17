
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    table_rows = soup.select('table.jobsTable tbody tr')

    data_list = []

    for row in table_rows[1:]:  # Skip the header row
        cols = row.find_all('td')
        if len(cols) < 5:
            continue

        announcement_name = cols[0].a.get_text(strip=True)
        link = cols[0].a['href']
        hd_job_category = cols[1].get('title', '').strip()
        hd_job_num = cols[2].get_text(strip=True)
        hd_loc = cols[3].get('title', '').strip()
        publish_time = cols[4].get_text(strip=True)

        data_list.append({
            "announcement_name": announcement_name,
            "publish_time": "",
            "link": link,
            "hd_dept": "",  # Assuming this field is not available in the provided HTML
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(data_list, f, ensure_ascii=False, indent=4)
