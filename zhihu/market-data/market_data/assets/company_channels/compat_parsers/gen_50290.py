
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for item in soup.find_all('div', class_='grid-item'):
        job_info = item.find('div', class_='job-info')
        job_title = job_info.find('span', class_='job-title').text.strip()
        job_link = job_info.find('a')['href']
        hd_hope_worktype = item.find('div', class_='job-type').text.strip()
        job_location = item.find('div', class_='job-location').text.strip()


        job_data = {
            "announcement_name": job_title,
            "publish_time": "",  # Assuming no publish time is provided in the HTML
            "link": job_link,
            "hd_dept": "",  # Assuming no department is provided in the HTML
            "hd_loc": job_location,
            "hd_job_num": "",  # Assuming no job number is provided in the HTML
            "hd_job_category": "",
            "hd_hope_worktype": hd_hope_worktype
        }

        job_list.append(job_data)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
