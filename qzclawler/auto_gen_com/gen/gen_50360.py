
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    rows = soup.select('tbody tr')
    data_list = []

    for row in rows:
        announcement_name = row.find('th').get_text(strip=True)
        publish_time = row.find('time', class_='date').get_text(strip=True)
        link = row.find('a')['href']
        hd_dept = ''  # Placeholder as the department is not provided in the HTML
        hd_loc = ''   # Placeholder as the location is not provided in the HTML
        hd_job_num = ''  # Placeholder as the job number is not provided in the HTML
        hd_job_category = ''  # Placeholder as the job category is not provided in the HTML

        data_list.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(data_list, f, ensure_ascii=False, indent=4)
