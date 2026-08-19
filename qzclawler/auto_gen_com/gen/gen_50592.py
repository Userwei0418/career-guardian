
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for item in soup.find_all("div", class_="style__STListItem-editor__sc-10r1nhd-0"):
        announcement_name = item.find("div", class_="style__STJobTitle-editor__sc-10r1nhd-4")
        announcement_name = announcement_name.get_text(strip=True) if announcement_name else ""
        
        publish_time = item.find("div", class_="style__STJobTime-editor__sc-10r1nhd-16")
        publish_time = publish_time.get_text(strip=True) if publish_time else ""
        

        link = ""
        
        hd_dept = item.find("div", class_="style__STLabelText-editor__sc-10r1nhd-13")
        hd_dept = hd_dept.get_text(strip=True) if hd_dept else ""
        
        hd_loc = item.find_all("div", class_="style__STLabelText-editor__sc-10r1nhd-13")[2]
        hd_loc = hd_loc.get_text(strip=True) if hd_loc else ""
        
        hd_job_num = ""  # Placeholder as the job number is not provided in the HTML
        hd_job_category = ""  # Placeholder as the job category is not provided in the HTML
        
        job_list.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": "",
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
