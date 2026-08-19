
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    table_rows = soup.find_all('tr')[1:]  # Skip the header row
    data_list = []

    for row in table_rows:
        cols = row.find_all('td')
        if len(cols) < 6:
            continue  # Skip rows that do not have enough columns

        announcement_name = cols[0].text.strip()
        hd_loc = cols[2].text.strip()
        hd_job_category = cols[3].text.strip()
        hd_job_num = cols[4].text.strip()
        publish_time = cols[5].text.strip()
        link = cols[6].find('a')['href'] if cols[6].find('a') else ''

        data_list.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": "",  # Placeholder as the department is not provided in the HTML
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(data_list, f, ensure_ascii=False, indent=4)
