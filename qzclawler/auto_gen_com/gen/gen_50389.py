
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for item in soup.find_all("div", class_="style__STListItem-editor__sc-10r1nhd-0"):
        title = item.find("div", class_="style__STJobTitle-editor__sc-10r1nhd-4").get_text(strip=True)
        location = item.find_all("div", class_="style__STLabelText-editor__sc-10r1nhd-13 cJYhpK")[1].get_text(strip=True)
        job_type = item.find_all("div", class_="style__STLabelText-editor__sc-10r1nhd-13 cJYhpK")[0].get_text(strip=True)
        
        # Assuming publish_time and link are not available in the provided HTML
        job_data = {
            "announcement_name": title,
            "publish_time": "",  # Placeholder as the data is not available
            "link": "",          # Placeholder as the data is not available
            "hd_dept": "",      # Placeholder as the data is not available
            "hd_loc": location,
            "hd_job_num": "",   # Placeholder as the data is not available
            "hd_job_category": job_type
        }
        
        job_list.append(job_data)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
