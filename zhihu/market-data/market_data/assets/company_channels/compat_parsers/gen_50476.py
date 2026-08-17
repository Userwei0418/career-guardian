
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    table_rows = soup.find_all('tr')[1:]  # Skip the header row
    job_list = []

    for row in table_rows:
        cols = row.find_all('td')
        if len(cols) < 5:
            continue  # Skip rows that do not have enough columns

        announcement_name = cols[0].get_text(strip=True)
        publish_time = cols[-1].get_text(strip=True)
        link = cols[0].find('a')['href'] if cols[0].find('a') else ""
        hd_dept = ""  # No data available in the provided HTML
        hd_loc = cols[3].get_text(strip=True)
        hd_job_num = ""  # No data available in the provided HTML
        hd_job_category = ""  # No data available in the provided HTML

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
