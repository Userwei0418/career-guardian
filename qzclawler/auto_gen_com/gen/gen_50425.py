
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []
    
    rows = soup.select('#showJobList tr')
    for row in rows:
        cols = row.find_all('td')
        if len(cols) >= 5:
            job_info = {
                "announcement_name": cols[0].a['title'],
                "publish_time": "",  # Placeholder as publish time is not provided in the HTML
                "link": cols[0].a['href'],
                "hd_dept": "",  # Placeholder as department is not provided in the HTML
                "hd_loc": cols[1].text.strip(),
                "hd_job_num": "",  # Placeholder as job number is not provided in the HTML
                "hd_job_category":""
            }
            job_list.append(job_info)
    
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
