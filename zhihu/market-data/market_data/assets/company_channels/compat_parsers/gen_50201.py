
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for container in soup.find_all("div", class_="container-aOp138AX_X"):
        job_info = {}
        link_tag = container.find("a", class_="link-txmgVOCVz9")
        job_info['announcement_name'] = link_tag.find("span", class_="title-u2qk9xX9Ie").text.strip()
        job_info['publish_time'] = link_tag.find("span", class_="published-at-PQ5IBWmbJV").text.replace("发布于 ", "").strip()
        job_info['link'] = link_tag['href']

        location = link_tag.find("div", class_="sd-Ellipsis-hiddenContent-1Skwh")
        job_info['hd_loc'] = location.text.strip() if location else ""

        # Placeholder values for missing fields
        job_info['hd_dept'] = ""
        job_info['hd_job_num'] = ""
        job_info['hd_job_category'] = ""

        job_list.append(job_info)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
