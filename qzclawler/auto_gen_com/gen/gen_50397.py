
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    # Extract job rows from the table
    rows = soup.select('tbody.ant-table-tbody tr')
    
    for row in rows:
        announcement_name = row.find('a').get('title').strip()
        hd_job_category = row.find_all('td')[1].text.strip()
        hd_dept = row.find_all('td')[2].text.strip()
        hd_loc = row.find_all('td')[3].text.strip()
        publish_time = row.find_all('td')[4].text.strip()
        hd_job_num = ""  # Placeholder as the job number is not provided in the HTML
        link = ""

        job_list.append({
            "announcement_name": announcement_name,
            "publish_time": "",
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        })

    # Write the job list to a JSON file
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
