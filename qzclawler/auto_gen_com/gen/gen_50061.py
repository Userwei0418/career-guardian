
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for card in soup.find_all('div', class_='container-aOp138AX_X'):
        announcement_name = card.find('span', class_='title-u2qk9xX9Ie').text.strip()
        link = card.find('a')['href']
        hd_dept = ""  # Assuming the department is not provided in the HTML
        hd_loc = ""
        hd_job_num = ""  # Assuming the job number is not provided in the HTML
        hd_job_category = card.find('div', class_='sd-Ellipsis-hiddenContent-1Skwh').text.strip() # Assuming the job category is not provided in the HTML
        publish_time = ""  # Assuming the publish time is not provided in the HTML

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
