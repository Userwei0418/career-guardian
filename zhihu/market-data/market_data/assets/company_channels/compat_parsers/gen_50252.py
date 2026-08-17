
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for item in soup.find_all("div", class_="style__STListItem-editor__sc-10r1nhd-0"):
        title = item.find("div", class_="style__STJobTitle-editor__sc-10r1nhd-4").get_text(strip=True)
        publish_time = item.find("div", class_="style__STJobTime-editor__sc-10r1nhd-16").get_text(strip=True).replace(" 发布", "")
        link = ""  # Assuming link extraction logic is not provided in the HTML
        hd_dept = ""  # Assuming a static value as it's not present in the HTML
        items = item.select('.style__STLabelSection-editor__sc-10r1nhd-11 .style__STLabelText-editor__sc-10r1nhd-13')
        print(items)
        work_loc_full = items[2].get_text(strip=True) if len(items) > 1 else ""
        print(work_loc_full)

        job_list.append({
            "announcement_name": title,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": work_loc_full,
            "hd_job_num": "",
            "hd_job_category": ""
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
