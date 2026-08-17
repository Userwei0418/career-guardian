
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    table_rows = soup.select('table.mg_t_50 tbody tr')[1:]  # Skip the header row
    announcements = []

    for row in table_rows:
        cols = row.find_all('td')
        announcement = {
            "announcement_name": cols[0].text.strip(),
            "hd_job_num": cols[1].text.strip(),
            "hd_loc": cols[2].text.strip(),
            "publish_time": cols[3].text.strip(),
            "link": cols[4].find('a')['href'],
            "hd_dept": "",  # Placeholder, as this information is not in the provided HTML
            "hd_job_category": ""  # Placeholder, as this information is not in the provided HTML
        }
        announcements.append(announcement)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(announcements, f, ensure_ascii=False, indent=4)
