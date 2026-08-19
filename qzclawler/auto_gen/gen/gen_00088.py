
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    announcements = []

    rows = soup.select('tr.el-table__row')
    for row in rows:
        announcement_name = row.select_one('td.el-table_1_column_1 .cell span').get_text(strip=True)
        hd_company = ""#row.select_one('td.el-table_1_column_2 .cell').get_text(strip=True)
        publish_time = row.select_one('td.el-table_1_column_3 .cell').get_text(strip=True)
        link = ""  # Assuming link is not provided in the HTML context

        announcements.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_company": hd_company
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(announcements, f, ensure_ascii=False, indent=4)