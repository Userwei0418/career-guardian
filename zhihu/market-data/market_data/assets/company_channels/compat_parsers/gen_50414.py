
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for item in soup.find_all("div", class_="style__STListItem-editor__sc-10r1nhd-0"):
        title = item.find("div", class_="style__STJobTitle-editor__sc-10r1nhd-4").get_text(strip=True)
        labels = item.find_all("div", class_="style__STLabelText-editor__sc-10r1nhd-13")
        location = labels[1].get_text(strip=True) if len(labels) > 1 else ""
        category = labels[2].get_text(strip=True) if len(labels) > 2 else ""

        job_info = {
            "announcement_name": title,
            "publish_time": "",  # Assuming no publish time is provided in the HTML
            "link": "",  # Assuming no link is provided in the HTML
            "hd_dept": "",  # Assuming the department is constant as per the example
            "hd_loc": location,
            "hd_job_num": "",  # Assuming no job number is provided in the HTML
            "hd_job_category": category
        }

        job_list.append(job_info)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
