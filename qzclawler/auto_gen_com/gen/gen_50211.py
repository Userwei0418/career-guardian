
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for container in soup.find_all("div", class_="container-aOp138AX_X"):
        link = container.find("a")["href"]
        title = container.find("span", class_="title-u2qk9xX9Ie").get_text(strip=True)
        publish_time = container.find("span", class_="published-at-PQ5IBWmbJV").get_text(strip=True).replace("发布于 ", "")
        hd_dept = ""  # Assuming the department is not provided in the HTML
        hd_loc = ""   # Assuming the location is not provided in the HTML
        hd_job_num = ""  # Assuming the job number is not provided in the HTML
        hd_job_category = ""  # Based on the content in the HTML

        job_list.append({
            "announcement_name": title,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
