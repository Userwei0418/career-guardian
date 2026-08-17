
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    job_cards = soup.find_all('div', class_='container-aOp138AX_X normal-TBuWTpDMcE list-oR2doUijv4')

    for card in job_cards:
        announcement_name = card.find('span', class_='title-u2qk9xX9Ie target-color-container').get_text(strip=True) if card.find('span', class_='title-u2qk9xX9Ie target-color-container') else ""
        link = card.find('a')['href'] if card.find('a') else ""
        publish_time = ""  # Assuming publish_time is not available in the provided HTML
        hd_dept = ""  # Assuming hd_dept is not available in the provided HTML
        hd_loc = ""  # Assuming hd_loc is not available in the provided HTML
        hd_job_num = ""  # Assuming hd_job_num is not available in the provided HTML
        hd_job_category = ""  # Assuming hd_job_category is not available in the provided HTML

        info_div = card.find('div', class_='info-tPG_0QGbhl')
        if info_div:
            job_details = info_div.find_all('div', class_='no-adaptive-tooltip')
            if len(job_details) >= 3:
                hd_job_num = job_details[0].get_text(strip=True)  # Assuming the first detail is job type
                hd_job_category = job_details[1].get_text(strip=True)  # Assuming the second detail is job category
                hd_loc = job_details[2].get_text(strip=True)  # Assuming the third detail is location
        if "实习" in announcement_name:
            hd_hopeworktype = "实习"
        else:
            hd_hopeworktype = ""
        job_list.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": "",
            "hd_job_category": hd_job_category,
            "hd_hopeworktype":hd_hopeworktype
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
