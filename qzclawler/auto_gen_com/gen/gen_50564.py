
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    rows = soup.find_all('div', class_='table-row')
    data_list = []

    for row in rows:
        cells = row.find_all('div', class_='table-cell')
        if len(cells) < 6:
            continue
        
        announcement_name = cells[0].get_text(strip=True) if len(cells) > 0 else ""
        hd_loc = cells[1].get_text(strip=True) if len(cells) > 1 else ""
        publish_time = cells[4].get_text(strip=True) if len(cells) > 4 else ""
        hd_job_category = cells[5].get_text(strip=True) if len(cells) > 5 else ""
        
        data_list.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": "",  # Assuming link is not provided in the HTML
            "hd_dept": "",  # Assuming hd_dept is not provided in the HTML
            "hd_loc": hd_loc,
            "hd_job_num": "",  # Assuming hd_job_num is not provided in the HTML
            "hd_job_category": hd_job_category
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(data_list, f, ensure_ascii=False, indent=4)
