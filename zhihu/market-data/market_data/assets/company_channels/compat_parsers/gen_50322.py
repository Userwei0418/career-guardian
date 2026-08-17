
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for item in soup.find_all("div", class_="style__STListItem-editor__sc-10r1nhd-0"):
        title = item.find("div", class_="style__STJobTitle-editor__sc-10r1nhd-4").get_text(strip=True)
        salary = item.find("div", class_="style__STJobSalary-editor__sc-10r1nhd-5").get_text(strip=True)
        location = item.find("div", class_="style__STLabelText-editor__sc-10r1nhd-13 cJYhpK").get_text(strip=True)

        # Extracting other details
        labels = item.find_all("div", class_="style__STLabelText-editor__sc-10r1nhd-13 cJYhpK")
        hd_dept = labels[-1].get_text(strip=True) if len(labels) > 1 else ""
        hd_loc = labels[-2].get_text(strip=True) if len(labels) > 1 else ""
        hd_job_num = ""  # Placeholder as the job number is not provided in the HTML
        hd_job_category = ""  # Placeholder as the job category is not provided in the HTML

        job_info = {
            "announcement_name": title,
            "publish_time": "",
            "link": "",  # Placeholder as the link is not provided in the HTML
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        }

        job_list.append(job_info)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
