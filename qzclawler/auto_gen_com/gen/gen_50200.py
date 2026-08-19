
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    job_items = soup.find_all(class_='style__STListItem-editor__sc-10r1nhd-0')
    
    for item in job_items:
        title = item.find(class_='style__STJobTitle-editor__sc-10r1nhd-4').get_text(strip=True)
        labels = item.find_all(class_='style__STLabelText-editor__sc-10r1nhd-13')
        location = labels[2].get_text(strip=True) if len(labels) > 2 else ''
        degree = labels[3].get_text(strip=True) if len(labels) > 3 else ''
        category = labels[4].get_text(strip=True) if len(labels) > 4 else ''
        
        job_info = {
            "announcement_name": title,
            "publish_time": "",  # Assuming publish_time is not available in the provided HTML
            "link": "",  # Assuming link is not available in the provided HTML
            "hd_dept": "",  # Assuming hd_dept is not available in the provided HTML
            "hd_loc": location,
            "hd_job_num": "",  # Assuming hd_job_num is not available in the provided HTML
            "hd_job_category": category
        }
        
        job_list.append(job_info)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
