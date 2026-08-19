
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    rows = soup.find_all('tr', class_='job_tr')
    for row in rows:
        cols = row.find_all('td')
        if len(cols) < 6:
            continue
        
        announcement_name = cols[2].get_text(strip=True) if len(cols) > 2 else ""
        publish_time = ""  # Assuming publish_time is not available in the provided HTML
        link = cols[2].find('a')['href'] if cols[2].find('a') else ""
        hd_dept = cols[0].get_text(strip=True) if len(cols) > 0 else ""
        hd_loc = cols[1].get_text(strip=True) if len(cols) > 1 else ""
        hd_job_num = ""  # Assuming hd_job_num is not available in the provided HTML
        hd_job_category = cols[3].get_text(strip=True) if len(cols) > 3 else ""

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
