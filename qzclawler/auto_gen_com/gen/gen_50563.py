
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    table_rows = soup.select('table.ph_table tbody tr')
    
    data_list = []
    
    for row in table_rows:
        cols = row.find_all('td')
        announcement_name = cols[0].get_text(strip=True) if len(cols) > 0 else ""
        hd_dept = cols[1].get_text(strip=True) if len(cols) > 1 else ""
        hd_loc = cols[2].get_text(strip=True) if len(cols) > 2 else ""
        publish_time = cols[4].get_text(strip=True) if len(cols) > 4 else ""
        hd_job_num = cols[5].get_text(strip=True) if len(cols) > 5 else ""
        link = cols[6].find('a')['href'] if len(cols) > 6 and cols[6].find('a') else ""
        hd_job_category = ""  # Assuming this field is not present in the HTML

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
