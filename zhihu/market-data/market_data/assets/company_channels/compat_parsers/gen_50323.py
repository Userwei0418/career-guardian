
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for item in soup.find_all("div", class_="style__STListItem-editor__sc-10r1nhd-0"):
        title = item.find("div", class_="style__STJobTitle-editor__sc-10r1nhd-4").get_text(strip=True)
        locations = item.find_all("div", class_="style__STLabelText-editor__sc-10r1nhd-13 cJYhpK")
        # Assuming publish_time and link are not available in the provided HTML
        location = locations[-1].get_text(strip=True) if locations else ""
        publish_time = ""
        link = ""
        hd_dept = ""
        hd_job_num = ""
        hd_job_category = ""

        job_list.append({
            "announcement_name": title,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": location,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
