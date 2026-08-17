
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    rows = soup.select('table tbody tr')
    for row in rows:
        cols = row.find_all('td')
        if len(cols) < 4:
            continue

        announcement_name = cols[0].get_text(strip=True)
        link = cols[0].find('a')['href']
        hd_dept = cols[1].get_text(strip=True)
        hd_loc = cols[2].get_text(strip=True)
        publish_time = cols[3].get_text(strip=True)
        hd_job_num = ""  # Assuming a default value as it's not provided in the HTML
        hd_job_category = ""  # Assuming a default value as it's not provided in the HTML

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
