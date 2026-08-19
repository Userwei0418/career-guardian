
import json
from bs4 import BeautifulSoup



def extract_table_from_html(htmlcontext, tempfile,page_url):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []
    print(page_url)
    rows = soup.select('#showJobList tr')
    for row in rows:
        cols = row.find_all('td')
        if len(cols) >= 5:
            job_info = {
                "announcement_name": cols[0].a['title'],
                "publish_time": "",  # Assuming publish_time is not available in the provided HTML
                "link": cols[0].a['href'],
                "hd_dept": "",  # Assuming hd_dept is not available in the provided HTML
                "hd_loc": cols[1].text.strip(),
                "hd_job_num": "",  # Assuming hd_job_num is not available in the provided HTML
                "hd_job_category": cols[2].text.strip()  # Assuming this is the job category
            }
            job_list.append(job_info)
    
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
