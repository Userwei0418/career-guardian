
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    items = soup.find_all('li', class_='search-item')
    
    result = []
    
    for item in items:
        announcement_name = item.find('span', class_='search-item-header-title-ellipsis').text.strip()
        publish_time = ""  # Assuming publish_time is not available in the provided HTML
        link = ""  # Assuming link is not available in the provided HTML
        hd_dept = ""  # Assuming department is constant based on the provided HTML
        hd_loc = item.find('span', class_='search-item-info-position').text.strip()
        hd_job_num = ""  # Assuming job number is not available in the provided HTML
        hd_job_category = ""  # Assuming job category is constant based on the provided HTML
        if "实习" in announcement_name:
            hd_hopeworktype = "实习"
        else:
            hd_hopeworktype = ""
        result.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category,
            "hd_hopeworktype":hd_hopeworktype
        })
    
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=4)
