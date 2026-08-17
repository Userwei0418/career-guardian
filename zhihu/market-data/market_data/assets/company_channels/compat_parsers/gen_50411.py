
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for item in soup.find_all("div", class_="style__STListItem-editor__sc-10r1nhd-0 dUmFMT"):
        title_section = item.find("div", class_="style__STTitleSection-editor__sc-10r1nhd-2 bhsAAi")
        job_title = title_section.find("div", class_="style__STJobTitle-editor__sc-10r1nhd-4 eVDXPD").get_text(strip=True)
        publish_time = item.find("div", class_="style__STJobTime-editor__sc-10r1nhd-16 eKeZsF").get_text(strip=True)

        other_section = item.find("div", class_="style__STOtherSection-editor__sc-10r1nhd-10 emrrHN")
        location = other_section.find_all("div", class_="style__STLabelText-editor__sc-10r1nhd-13 cJYhpK")[1].get_text(strip=True)
        job_num = other_section.find_all("div", class_="style__STLabelText-editor__sc-10r1nhd-13 cJYhpK")[2].get_text(strip=True)

        # Assuming the link is not provided in the HTML, we can set it to None or an empty string
        link = ""

        job_info = {
            "announcement_name": job_title,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": "",  # Placeholder as the department is not provided in the HTML
            "hd_loc": location,
            "hd_job_num": "",
            "hd_job_category": ""  # Placeholder as the job category is not provided in the HTML
        }

        job_list.append(job_info)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
