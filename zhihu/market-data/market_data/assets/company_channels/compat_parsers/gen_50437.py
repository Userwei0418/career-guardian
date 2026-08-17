
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    rows = soup.select('.table-body .table-row')
    for row in rows:
        cells = row.select('.table-cell')
        if len(cells) >= 6:
            job_info = {
                "announcement_name": cells[0].get_text(strip=True),
                "publish_time": cells[4].get_text(strip=True),
                "link": "",  # Assuming link is not provided in the HTML
                "hd_dept": "",  # Assuming department is not provided in the HTML
                "hd_loc": cells[1].get_text(strip=True),
                "hd_job_num": "",  # Assuming job number is not provided in the HTML
                "hd_job_category": ""
            }
            job_list.append(job_info)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
