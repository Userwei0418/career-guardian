import json
from bs4 import BeautifulSoup

def safe_get_text(element, default=''):
    """安全获取文本，如果 element 为 None，则返回默认值"""
    return element.get_text(strip=True) if element else default

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for item in soup.find_all("div", class_="style__STListItem-editor__sc-10r1nhd-0"):
        title_section = item.find("div", class_="style__STTitleSection-editor__sc-10r1nhd-2")

        job_title = safe_get_text(title_section.find("div", class_="style__STJobTitle-editor__sc-10r1nhd-4"))
        job_time = safe_get_text(title_section.find("div", class_="style__STJobTime-editor__sc-10r1nhd-16"))
        location = safe_get_text(title_section.find("div", class_="style__STLabelText-editor__sc-10r1nhd-13"))
        job_salary = safe_get_text(title_section.find("div", class_="style__STJobSalary-editor__sc-10r1nhd-5"))

        job_labels = title_section.find_all("div", class_="style__STLabelText-editor__sc-10r1nhd-13")
        job_labels_text = [safe_get_text(label) for label in job_labels]

        hd_dept = job_labels_text[0] if len(job_labels_text) > 0 else ""
        hd_job_category = job_labels_text[1] if len(job_labels_text) > 1 else ""

        job_entry = {
            "announcement_name": job_title,
            "publish_time": job_time,
            "link": "",  # HTML 中没有提供链接就保持为空
            "hd_dept": hd_dept,
            "hd_loc": location,
            "hd_job_num": "",  # HTML 中没有提供招聘人数就保持为空
            "hd_job_category": hd_job_category
        }

        job_list.append(job_entry)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
