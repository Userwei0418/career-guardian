
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_items = soup.find_all('div', class_='job-item-O5PbSds8YJ')

    job_list = []

    for item in job_items:
        link = item.find('a', class_='job-Rj80rYM8EN')['href']
        title = item.find('span', class_='ellipsis-s4h2VX0z8O').text.strip()
        status_info = item.find('div', class_='list-status-KtkIHmfTWp')
        department = ""
        location =""

        job_entry = {
            "announcement_name": title,
            "publish_time": "",  # Assuming publish_time is not available in the provided HTML
            "link": link,
            "hd_dept": department,
            "hd_loc": location,
            "hd_job_num": "",  # Assuming hd_job_num is not available in the provided HTML
            "hd_job_category": ""  # Assuming hd_job_category is not available in the provided HTML
        }

        job_list.append(job_entry)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
