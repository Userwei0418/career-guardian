
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    data_list = []

    rows = soup.find_all('div', class_='table-row')
    for row in rows:
        cells = row.find_all('div', class_='table-cell')
        if len(cells) >= 5:  # Ensure there are enough cells
            announcement_name = cells[0].get_text(strip=True)
            hd_dept = cells[1].get_text(strip=True)
            hd_job_category = cells[2].get_text(strip=True)
            hd_job_num = cells[3].get_text(strip=True)
            hd_loc = cells[4].get_text(strip=True)
            publish_time = ""  # Placeholder for publish_time, as it's not in the provided HTML

            data_list.append({
                "announcement_name": announcement_name,
                "publish_time": publish_time,
                "link": "",  # Placeholder for link, as it's not in the provided HTML
                "hd_dept": hd_dept,
                "hd_loc": hd_loc,
                "hd_job_num": hd_job_num,
                "hd_job_category": hd_job_category
            })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(data_list, f, ensure_ascii=False, indent=4)
