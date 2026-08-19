
import json
from bs4 import BeautifulSoup

def extract_table_from_html(html_content, tempfile):
    soup = BeautifulSoup(html_content, 'html.parser')
    table_rows = soup.select('#tabGrid tbody tr')
    announcements = []

    for row in table_rows:
        cells = row.find_all('td')
        if len(cells) >= 6:
            announcement_name = cells[4].get_text(strip=True)
            publish_time = cells[5].get_text(strip=True)
            link = cells[3].find('a')['onclick'].split('"')[1]  # Extracting id from onclick
            link = f"http://career.ouc.edu.cn/zftal-web/zfjy!ykfw/zpztgl_cxWzZpxxNry.html?id={link}&zpdxdm=1"
            announcements.append({
                'announcement_name': announcement_name,
                'publish_time': publish_time,
                'link': link
            })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(announcements, f, ensure_ascii=False, indent=4)