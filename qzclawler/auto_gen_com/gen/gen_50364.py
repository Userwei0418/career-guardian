
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for item in soup.find_all("div", class_="style__STListItem-editor__sc-10r1nhd-0"):
        title_section = item.find("div", class_="style__STTitleSection-editor__sc-10r1nhd-2")
        job_title = title_section.find("div", class_="style__STJobTitle-editor__sc-10r1nhd-4").get_text(strip=True)
        job_time = title_section.find("div", class_="style__STJobTime-editor__sc-10r1nhd-16").get_text(strip=True)
        location = title_section.find("div", class_="style__STLabelText-editor__sc-10r1nhd-13").get_text(strip=True)
        
        # Extracting other details
        job_salary = title_section.find("div", class_="style__STJobSalary-editor__sc-10r1nhd-5").get_text(strip=True)
        job_labels = title_section.find_all("div", class_="style__STLabelText-editor__sc-10r1nhd-13")
        job_labels_text = [label.get_text(strip=True) for label in job_labels]
        
        # Assuming the first label is the department and the second is the job category
        hd_dept = job_labels_text[0] if len(job_labels_text) > 0 else ""
        hd_job_category = job_labels_text[1] if len(job_labels_text) > 1 else ""
        
        # Creating a job entry
        job_entry = {
            "announcement_name": job_title,
            "publish_time": job_time,
            "link": "",  # Assuming no link is provided in the HTML
            "hd_dept": hd_dept,
            "hd_loc": location,
            "hd_job_num": "",  # Assuming no job number is provided in the HTML
            "hd_job_category": hd_job_category
        }
        
        job_list.append(job_entry)

    # Write to JSON file
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
