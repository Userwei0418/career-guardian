
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    announcements = []

    for item in soup.find_all("div", class_="style__STListItem-editor__sc-10r1nhd-0"):
        announcement = {}

        # Extracting announcement name
        title_div = item.find("div", class_="style__STJobTitle-editor__sc-10r1nhd-4")
        announcement["announcement_name"] = title_div.get_text(strip=True) if title_div else ""

        # Extracting publish time (not present in the provided HTML, so set to None)
        announcement["publish_time"] = ""

        # Extracting link (not present in the provided HTML, so set to None)
        announcement["link"] = ""

        # Extracting department or institution (not present in the provided HTML, so set to None)
        announcement["hd_dept"] = ""

        # Extracting work location (not present in the provided HTML, so set to None)
        announcement["hd_loc"] = ""

        # Extracting job number (not present in the provided HTML, so set to None)
        announcement["hd_job_num"] = ""

        # Extracting job category
        label_div = item.find("div", class_="style__STLabelText-editor__sc-10r1nhd-13")
        announcement["hd_job_category"] = label_div.get_text(strip=True) if label_div else None

        announcements.append(announcement)

    # Writing to JSON file
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(announcements, f, ensure_ascii=False, indent=4)
