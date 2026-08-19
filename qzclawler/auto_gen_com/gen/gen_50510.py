
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    rows = soup.select('.table-body .table-row')
    for row in rows:
        cells = row.select('.table-cell')
        if len(cells) < 6:
            continue
        
        job_info = {
            "announcement_name": cells[0].get_text(strip=True) if len(cells) > 0 else "",
            "publish_time": "",  # Assuming this information is not available in the provided HTML
            "link": "",  # Assuming this information is not available in the provided HTML
            "hd_dept": cells[1].get_text(strip=True) if len(cells) > 1 else "",
            "hd_loc": cells[2].get_text(strip=True) if len(cells) > 2 else "",
            "hd_job_num": "",  # Assuming this information is not available in the provided HTML
            "hd_job_category": cells[5].get_text(strip=True) if len(cells) > 5 else ""
        }
        job_list.append(job_info)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
