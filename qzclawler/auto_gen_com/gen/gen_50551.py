
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    table_rows = soup.select('table.j_table tbody tr')
    
    data_list = []
    
    for row in table_rows:
        cols = row.find_all('td')
        if len(cols) >= 4:
            announcement_name = cols[0].get_text(strip=True)
            link = cols[0].find('a')['href'] if cols[0].find('a') else ""
            hd_loc = cols[1].get_text(strip=True)
            hd_job_num = cols[2].get_text(strip=True)
            publish_time = cols[3].get_text(strip=True)
            hd_dept = ""  # No data available in the provided HTML
            hd_job_category = cols[4].get_text(strip=True) if len(cols) > 4 else ""
            
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
