
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    table_rows = soup.select('table.newsTable tbody tr')

    announcements = []

    for row in table_rows:
        announcement_name = row.find('a').text
        publish_time = row.find('td', align='center').text
        link = row.find('a')['href']
        hd_company = ''  # Assuming company name is not provided in the HTML

        announcements.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_company": hd_company
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(announcements, f, ensure_ascii=False, indent=4)