
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    table_rows = soup.select('table.jobsTable tbody tr')
    
    job_list = []
    
    for row in table_rows[1:]:  # Skip the header row
        cols = row.find_all('td')
        if len(cols) < 4:
            continue
        
        announcement_name = cols[0].find('a').get('title')
        link = cols[0].find('a').get('href')
        publish_time = cols[3].text.strip()
        hd_job_num = cols[1].text.strip()
        hd_loc = cols[2].get('title', '').strip()
        hd_dept = ''  # Placeholder as the data does not provide this
        hd_job_category = ''  # Placeholder as the data does not provide this
        
        job_list.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        })
    
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
