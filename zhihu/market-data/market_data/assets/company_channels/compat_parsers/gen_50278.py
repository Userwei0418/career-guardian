
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for card in soup.find_all(class_='card-wrapper'):
        announcement_name = card.find(class_='name').text.strip()
        hd_dept = card.find(class_='deptName').text.strip()
        hd_loc = card.find(class_='work-city').find_all('span')[1].text.strip()
        hd_job_category = card.find(class_='type').text.strip()
        # Assuming publish_time and link are not available in the provided HTML
        publish_time = ""
        link = ""
        hd_job_num = ""  # Assuming job number is not available in the provided HTML

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
