
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    rows = soup.find_all('div', class_=['row0', 'row1'])
    for row in rows:
        announcement_name = row.h3.a.text.strip()
        link = row.h3.a['href']
        details = row.find('div', class_='details')
        
        hd_dept = details.find_all('p')[3].text.split(':')[1].strip()
        publish_time = details.find_all('p')[4].text.split(':')[1].strip()
        hd_loc = details.find_all('p')[2].text.split(':')[1].strip()
        hd_job_num = details.find_all('p')[2].text.split(':')[1].strip()  # Assuming this is the job number
        hd_job_category = details.find_all('p')[1].text.split(':')[1].strip()  # Assuming this is the job category
        
        job_list.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": "",
            "hd_job_category": hd_job_category
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
