from bs4 import BeautifulSoup
import json

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    table_data = []

    for row in soup.select('tr.el-table__row'):
        columns = row.select('td')
        if len(columns) >= 2:
            announcement_name = columns[0].select_one('span.el-link--inner').text.strip() if columns[0].select_one('span.el-link--inner') else ''
            publish_time = columns[1].select_one('.cell').text.strip() if columns[1].select_one('.cell') else ''
            link = ''  # HTML中没有提供实际链接，保留为空

            table_data.append({
                'announcement_name': announcement_name,
                'publish_time': publish_time,
                'link': link
            })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(table_data, f, ensure_ascii=False, indent=2)