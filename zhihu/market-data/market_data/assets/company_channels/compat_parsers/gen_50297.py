
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    rows = soup.find_all('tr')
    data_list = []

    for row in rows:
        cells = row.find_all('td')
        if len(cells) < 6:
            continue

        announcement_name = cells[0].get('title', '').strip()
        hd_job_category = cells[1].get_text(strip=True).replace('族','')
        hd_job_num = cells[2].get_text(strip=True)
        hd_loc = cells[3].get('title', '').strip()
        publish_time = cells[4].get_text(strip=True)
        link = ""  # Placeholder for the link, as the actual link is not provided in the HTML

        data_list.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": "",  # Assuming the department is the same for all
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(data_list, f, ensure_ascii=False, indent=4)
