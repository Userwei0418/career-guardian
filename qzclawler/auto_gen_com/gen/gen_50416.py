
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for item in soup.find_all("div", class_="style__STListItem-editor__sc-10r1nhd-0"):
        title_section = item.find("div", class_="style__STTitleSection-editor__sc-10r1nhd-2")
        job_title = title_section.find("div", class_="style__STJobTitle-editor__sc-10r1nhd-4").get_text(strip=True)
        job_id = job_title.split('(')[-1].strip(')')  # Extract job ID from title
        job_name = job_title.split('(')[0].strip()  # Extract job name

        other_section = item.find("div", class_="style__STOtherSection-editor__sc-10r1nhd-10")
        job_time = other_section.find("div", class_="style__STJobTime-editor__sc-10r1nhd-16").get_text(strip=True)
        location = other_section.find_all("div", class_="style__STLabelText-editor__sc-10r1nhd-13")[2].get_text(strip=True)

        # Assuming the link is not provided in the HTML snippet, we can set it to None or an empty string
        link = ""

        # Create a job entry
        job_entry = {
            "announcement_name": job_name,
            "publish_time": job_time,
            "link": link,
            "hd_dept": "",  # Placeholder as the department is not provided
            "hd_loc": location,
            "hd_job_num": "",  # Placeholder as the job number is not provided
            "hd_job_category": ""  # Placeholder as the job category is not provided
        }

        job_list.append(job_entry)

    # Write the job list to a JSON file
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
