
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    table_rows = soup.select('#searchresults tbody .data-row')
    
    job_list = []
    
    for row in table_rows:
        title_tag = row.select_one('.colTitle .jobTitle-link')
        location_tag = row.select_one('.colLocation .jobLocation')
        
        if title_tag and location_tag:
            job_info = {
                "announcement_name": title_tag.get_text(strip=True),
                "publish_time": "",  # Placeholder as the HTML does not provide this information
                "link": title_tag['href'],
                "hd_dept": "",  # Placeholder as the HTML does not provide this information
                "hd_loc": location_tag.get_text(strip=True).replace("CN", ""),
                "hd_job_num": "",  # Placeholder as the HTML does not provide this information
                "hd_job_category": ""  # Placeholder as the HTML does not provide this information
            }
            job_list.append(job_info)
    
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
