
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    table_rows = soup.select('table.table tbody tr.table-tr')
    
    job_list = []
    
    for row in table_rows:
        cells = row.find_all('td')
        if len(cells) < 5:
            continue
        
        announcement_name = cells[0].get_text(strip=True)
        hd_job_num = cells[1].get_text(strip=True)
        hd_dept = cells[2].get_text(strip=True)
        hd_loc = cells[3].get_text(strip=True)
        link = cells[4].find('a')['href']
        
        # Extracting the positionTime from the onclick attribute
        onclick_data = cells[5].find('a')['onclick']
        position_time = onclick_data.split('"positionTime":"')[1].split('"')[0]
        
        job_info = {
            "announcement_name": announcement_name,
            "publish_time": position_time,
            "link": link,
            "hd_dept": "",
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": ""  # Placeholder as the category is not provided in the HTML
        }
        
        job_list.append(job_info)
    
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
