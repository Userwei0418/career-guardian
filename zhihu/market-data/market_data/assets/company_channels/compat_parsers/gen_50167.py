
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    rows = soup.select('tbody tr')

    data_list = []

    for row in rows:
        cols = row.find_all('td')
        if len(cols) >= 3:
            announcement_name = cols[0].get_text(strip=True)
            hd_loc = cols[1].get_text(strip=True)
            link = cols[2].find('a')['href']

            # Assuming other fields are not available in the provided HTML
            data = {
                "announcement_name": announcement_name,
                "publish_time": "",  # Placeholder as it's not provided
                "link": link,
                "hd_dept": "",  # Placeholder as it's not provided
                "hd_loc": hd_loc,
                "hd_job_num": "",  # Placeholder as it's not provided
                "hd_job_category": ""  # Placeholder as it's not provided
            }
            data_list.append(data)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(data_list, f, ensure_ascii=False, indent=4)
