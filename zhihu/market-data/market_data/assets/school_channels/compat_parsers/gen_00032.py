
import json
from bs4 import BeautifulSoup

def extract_table_from_html(html_context, temp_file):
    soup = BeautifulSoup(html_context, 'html.parser')
    announcements = []

    rows = soup.select('tbody.ant-table-tbody tr.ant-table-row')
    for row in rows:
        announcement_name_tag = row.select_one('td.ant-table-row-cell-break-word a')
        if announcement_name_tag:
            announcement_name = announcement_name_tag.get_text(strip=True)
            link = announcement_name_tag['href']
            publish_time = row.select_one('td.ant-table-row-cell-break-word:nth-of-type(3) span').get_text(strip=True)

            announcements.append({
                "announcement_name": announcement_name,
                "publish_time": publish_time,
                "link": link
            })

    with open(temp_file, 'w', encoding='utf-8') as f:
        json.dump(announcements, f, ensure_ascii=False, indent=4)