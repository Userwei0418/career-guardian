
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    table_rows = soup.select('#result tbody tr')

    data_list = []

    for row in table_rows:
        cells = row.find_all('td')
        if len(cells) >= 5:
            announcement_name = cells[1].get_text(strip=True)
            link = cells[1].find('a')['href']
            hd_dept = cells[3].get_text(strip=True)
            hd_loc = ""  # Placeholder as the HTML does not provide this information
            hd_job_num = ""  # Placeholder as the HTML does not provide this information
            hd_job_category = cells[3].get_text(strip=True)
            publish_time = ""  # Placeholder as the HTML does not provide this information

            data_list.append({
                "announcement_name": announcement_name,
                "publish_time": publish_time,
                "link": link,
                "hd_dept": "",
                "hd_loc": hd_loc,
                "hd_job_num": hd_job_num,
                "hd_job_category": hd_job_category
            })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(data_list, f, ensure_ascii=False, indent=4)
