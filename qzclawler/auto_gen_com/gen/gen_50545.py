
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    rows = soup.select('.zwlbm tbody tr')
    for row in rows:
        cols = row.find_all('td')
        if len(cols) < 6:
            continue
        
        announcement_name = cols[0].get_text(strip=True) or ""
        hd_job_category = cols[1].get_text(strip=True) or ""
        hd_loc = cols[2].get_text(strip=True) or ""
        publish_time = cols[3].get_text(strip=True) or ""
        deadline = cols[4].get_text(strip=True) or ""
        link = cols[0].find('a')['href'] if cols[0].find('a') else ""
        
        job_list.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_job_category.split('-')[0] if '-' in hd_job_category else "",
            "hd_loc": hd_loc,
            "hd_job_num": "",  # No data available in the provided HTML
            "hd_job_category": hd_job_category
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
