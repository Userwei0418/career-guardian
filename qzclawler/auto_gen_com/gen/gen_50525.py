
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for li in soup.select('ul.clist > li'):
        announcement_name = li.h3.a.get_text(strip=True) if li.h3.a else ""
        link = li.h3.a['href'] if li.h3.a else ""
        hd_dept = li.find('span', text=True).get_text(strip=True) if li.find('span', text=True) else ""
        hd_loc = li.find_all('span')[1].get_text(strip=True) if len(li.find_all('span')) > 1 else ""
        hd_job_num = ""  # Assuming this information is not available in the provided HTML
        hd_job_category = ""  # Assuming this information is not available in the provided HTML
        publish_time = ""  # Assuming this information is not available in the provided HTML
        if "校招" in announcement_name:
            hd_hopeworktype = "校招"
        elif "实习" in announcement_name:
            hd_hopeworktype = "实习"
        else:
            hd_hopeworktype = ""
        job_list.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category,
            "hd_hopeworktype": hd_hopeworktype
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
