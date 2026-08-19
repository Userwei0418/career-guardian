
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    table_rows = soup.select('table.jobsTable tbody tr')
    
    job_list = []
    
    for row in table_rows[1:]:  # Skip the header row
        cols = row.find_all('td')
        if len(cols) < 5:
            continue
        
        announcement_name = cols[0].get_text(strip=True)
        link = cols[0].a['href'] if cols[0].a else ""
        hd_dept = cols[2].get_text(strip=True) if len(cols) > 2 else ""
        hd_loc = cols[4].get_text(strip=True) if len(cols) > 4 else ""
        hd_job_num = cols[3].get_text(strip=True) if len(cols) > 3 else ""
        hd_job_category = cols[1].get_text(strip=True) if len(cols) > 1 else ""
        if '实习' in announcement_name:
            hd_hopeworktype = "实习"
        else:
            hd_hopeworktype = ""
        job_list.append({
            "announcement_name": announcement_name,
            "publish_time": "",  # Assuming publish_time is not available in the provided HTML
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category,
            "hd_hopeworktype": hd_hopeworktype
        })
    
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
