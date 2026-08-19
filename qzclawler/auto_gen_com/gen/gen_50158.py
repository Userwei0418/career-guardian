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

        announcement = {
            "announcement_name": cells[0].get_text(strip=True),
            "hd_dept": cells[1].get_text(strip=True),
            "hd_loc": cells[2].get_text(strip=True),
            "publish_time": cells[4].get_text(strip=True),
            "hd_job_num": "",  # Placeholder as the data is not provided in the HTML
            "hd_job_category": cells[5].get_text(strip=True),
            "link": "",  # Placeholder as the link is not provided in the HTML
        }

        data_list.append(announcement)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(data_list, f, ensure_ascii=False, indent=4)
