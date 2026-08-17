
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for item in soup.find_all('div', class_='style__STListItem-editor__sc-10r1nhd-0'):
        announcement_name = item.find('div', class_='style__STJobTitle-editor__sc-10r1nhd-4')
        announcement_name = announcement_name.get_text(strip=True) if announcement_name else ""

        publish_time = item.find('div', class_='style__STJobTime-editor__sc-10r1nhd-16')
        publish_time = publish_time.get_text(strip=True).replace(" 发布", "") if publish_time else ""

        link = ""  # Assuming no link is provided in the HTML structure

        hd_dept = ""  # Assuming no department is provided in the HTML structure
        hd_loc = item.find_all('div', class_='style__STLabelText-editor__sc-10r1nhd-13')[2]
        hd_loc = hd_loc.get_text(strip=True) if hd_loc else ""

        hd_job_num = ""  # Assuming no job number is provided in the HTML structure
        hd_job_category = ""  # Assuming no job category is provided in the HTML structure

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
