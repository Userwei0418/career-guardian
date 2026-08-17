
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    rows = soup.find_all('tr', class_=['srJobListJobOdd', 'srJobListJobEven'])
    for row in rows:
        job_title = row.find('td', class_='srJobListJobTitle').text.strip()
        department = row.find('td', class_='srJobListDepartment').text.strip()
        location = row.find('td', class_='srJobListLocation').text.strip()
        link = row['onclick'].split('"')[1]

        job_info = {
            "announcement_name": job_title,
            "publish_time": "",  # Assuming publish_time is not available in the provided HTML
            "link": link,
            "hd_dept": department,
            "hd_loc": location,
            "hd_job_num": "",  # Assuming hd_job_num is not available in the provided HTML
            "hd_job_category": ""  # Assuming hd_job_category is not available in the provided HTML
        }
        job_list.append(job_info)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
