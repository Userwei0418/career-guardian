
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    data_list = []

    rows = soup.select('tbody.ant-table-tbody tr.ant-table-row')
    for row in rows:
        announcement_name = row.select_one('td div span').text
        publish_time = row.select_one('td.ant-table-row-cell-break-word span').text
        link = ''  # Assuming the link needs to be extracted but is not present in the provided HTML structure
        
        data_list.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(data_list, f, ensure_ascii=False, indent=4)