
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    table_rows = soup.find_all('tr')[1:]  # Skip the header row
    data_list = []

    for row in table_rows:
        cols = row.find_all('td')
        if len(cols) < 5:
            continue  # Skip rows that do not have enough columns

        announcement_name = cols[0].text.strip()
        link = cols[0].find('a')['href']
        hd_dept = cols[1].text.strip()
        hd_job_num = cols[2].text.strip() or ''  # Default to 'N/A' if empty
        hd_loc = cols[3].text.strip()
        publish_time = cols[4].text.strip()
        hd_job_category = hd_dept  # Assuming job category is the same as department

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
