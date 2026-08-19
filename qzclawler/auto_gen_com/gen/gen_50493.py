
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    rows = soup.find_all('tr', class_='tablezw0') + soup.find_all('tr', class_='tablezw1')
    
    data_list = []
    
    for row in rows:
        cols = row.find_all('td')
        if len(cols) >= 3:
            announcement_name = cols[0].get_text(strip=True) if cols[0].a else ""
            link = cols[0].a['href'] if cols[0].a else ""
            hd_job_category = cols[1].get_text(strip=True) if len(cols) > 1 else ""
            hd_loc = cols[2].get_text(strip=True) if len(cols) > 2 else ""
            
            data_list.append({
                "announcement_name": announcement_name,
                "publish_time": "",  # Assuming this field is not available in the provided HTML
                "link": link,
                "hd_dept": "",  # Assuming this field is not available in the provided HTML
                "hd_loc": hd_loc,
                "hd_job_num": "",  # Assuming this field is not available in the provided HTML
                "hd_job_category": hd_job_category
            })
    
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(data_list, f, ensure_ascii=False, indent=4)
