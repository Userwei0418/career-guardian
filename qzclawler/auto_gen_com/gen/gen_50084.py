
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    table = soup.find('table', {'id': 'wdresults'})
    rows = table.find_all('tr')[1:]  # Skip the header row

    job_list = []

    for row in rows:
        cols = row.find_all('td')
        if len(cols) < 6:
            continue  # Skip rows that do not have enough columns

        announcement_name = cols[0].get_text(strip=True)
        job_id = cols[1].get_text(strip=True)
        hd_loc = cols[2].get_text(strip=True)
        hd_dept = cols[3].get_text(strip=True)
        hd_job_category = cols[4].get_text(strip=True)
        hd_job_num = cols[5].get_text(strip=True)
        link = cols[0].find('a')['href']

        job_list.append({
            "announcement_name": announcement_name,
            "publish_time": "",  # Assuming job_id is used as publish_time
            "link": link,
            "hd_dept": "",
            "hd_loc": hd_loc,
            "hd_job_num": "",
            "hd_job_category": ""
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
