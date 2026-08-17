
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for item in soup.find_all("div", class_="style__STListItem-editor__sc-10r1nhd-0"):
        title = item.find("div", class_="style__STJobTitle-editor__sc-10r1nhd-4").get_text(strip=True)
        time_info = item.find("div", class_="style__STJobTime-editor__sc-10r1nhd-16").get_text(strip=True)
        publish_time = time_info.split(" ")[0]  # Extracting the date part
        link = ""  # Placeholder for link, as the link is not provided in the HTML
        dept_loc = item.find("div", class_="style__STLabelSection-editor__sc-10r1nhd-11").find_all("div", class_="style__STLabelText-editor__sc-10r1nhd-13")
        hd_dept = ""
        hd_loc = ""
        hd_job_num = ""  # Placeholder for job number, as the number is not provided in the HTML
        hd_job_category = ""  # Placeholder for job category, as the category is not provided in the HTML

        job_list.append({
            "announcement_name": title,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
