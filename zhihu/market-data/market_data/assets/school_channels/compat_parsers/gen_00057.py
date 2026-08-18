
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    table_rows = soup.select('table.am-table tbody tr')

    announcements = []

    for row in table_rows:
        cols = row.find_all('td')
        if len(cols) >= 4:
            announcement_name = cols[0].get_text(strip=True)
            publish_time = cols[3].get_text(strip=True)
            link = cols[0].find('a')['href']
            company_name = cols[1].get_text(strip=True)

            announcements.append({
                "announcement_name": announcement_name,
                "publish_time": publish_time,
                "link": link,
                "hd_company": company_name
            })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(announcements, f, ensure_ascii=False, indent=4)