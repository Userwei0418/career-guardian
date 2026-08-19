
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for job_card in soup.find_all('div', class_='container-aOp138AX_X'):
        announcement_name = job_card.find('span', class_='title-u2qk9xX9Ie').text.strip()
        link = job_card.find('a')['href']
        # Assuming publish_time is not available in the provided HTML
        publish_time = ""
        hd_dept = ""
        hd_loc = job_card.find_all('div', class_='sd-Ellipsis-hiddenContent-1Skwh')[1].text.strip()
        hd_job_num ="" # Assuming job number is not available in the provided HTML
        hd_job_category = job_card.find('div', class_='sd-Ellipsis-hiddenContent-1Skwh').text.strip().replace('-校招', '')  # Using department as job category for this example

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
