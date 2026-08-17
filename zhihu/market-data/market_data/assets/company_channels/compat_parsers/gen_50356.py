
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for container in soup.find_all("div", class_="container-aOp138AX_X"):
        job_info = {}
        link_tag = container.find("a", class_="link-txmgVOCVz9")
        job_info['announcement_name'] = link_tag.find("span", class_="title-u2qk9xX9Ie").text.strip()
        job_info['link'] = link_tag['href']
        job_info['hd_dept'] = container.find("div", class_="sd-Ellipsis-hiddenContent-1Skwh").text.strip()
        job_info['hd_loc'] = ""  # Assuming hd_loc is the same as hd_dept based on the provided HTML
        job_info['hd_job_num'] = ""  # Placeholder as the HTML does not provide this information
        job_info['hd_job_category'] = ""  # Placeholder as the HTML does not provide this information
        job_info['publish_time'] = ""  # Placeholder as the HTML does not provide this information

        job_list.append(job_info)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
