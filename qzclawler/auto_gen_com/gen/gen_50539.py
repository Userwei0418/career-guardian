
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for item in soup.find_all("div", class_="style__STListItem-editor__sc-10r1nhd-0"):
        announcement_name = item.find("div", class_="style__STJobTitle-editor__sc-10r1nhd-4").get_text(strip=True) if item.find("div", class_="style__STJobTitle-editor__sc-10r1nhd-4") else ""
        publish_time = item.find("div", class_="style__STJobTime-editor__sc-10r1nhd-16").get_text(strip=True) if item.find("div", class_="style__STJobTime-editor__sc-10r1nhd-16") else ""
        link = ""  # Assuming no link is provided in the HTML
        hd_dept = ""
        hd_loc = ""
        hd_job_num = ""
        hd_job_category = ""

        labels = item.find_all("div", class_="style__STJobLabel-editor__sc-10r1nhd-12")
        hd_dept = labels[3].get_text(strip=True)
        for label in labels:
            label_text = label.find("div", class_="style__STLabelText-editor__sc-10r1nhd-13").get_text(strip=True) if label.find("div", class_="style__STLabelText-editor__sc-10r1nhd-13") else ""
            if "招聘" in label_text:
                hd_job_num = ""
            elif "地点" in label_text:
                hd_loc = ""

            else:
                hd_job_category = ""

        job_list.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
