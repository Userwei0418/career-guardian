
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for item in soup.find_all('div', class_='style__STListItem-editor__sc-10r1nhd-0'):
        announcement_name = item.find('div', class_='style__STJobTitle-editor__sc-10r1nhd-4').get_text(strip=True) if item.find('div', class_='style__STJobTitle-editor__sc-10r1nhd-4') else ""
        publish_time = item.find('div', class_='style__STJobTime-editor__sc-10r1nhd-16').get_text(strip=True).replace(" 发布", "") if item.find('div', class_='style__STJobTime-editor__sc-10r1nhd-16') else ""
        link = ""  # Assuming link extraction is not provided in the HTML
        hd_dept = ""  # Assuming department extraction is not provided in the HTML
        hd_loc = item.find_all('div', class_='style__STLabelText-editor__sc-10r1nhd-13 cJYhpK')[2].get_text(strip=True) if item.find('div', class_='style__STLabelText-editor__sc-10r1nhd-13 cJYhpK') else ""
        hd_job_num = ""  # Assuming job number extraction is not provided in the HTML
        hd_job_category = item.find('div', class_='style__STLabelText-editor__sc-10r1nhd-13 cJYhpK').get_text(strip=True) if item.find('div', class_='style__STLabelText-editor__sc-10r1nhd-13 cJYhpK') else ""
  # Assuming job category extraction is not provided in the HTML
        if '社会招聘' in hd_job_category:
            hd_hopeworktype = "社招"
        else:
            hd_hopeworktype = ""
        job_list.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": "",
            "hd_hopeworktype": hd_hopeworktype
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
