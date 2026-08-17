
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    job_cards = soup.find_all('div', class_='container-aOp138AX_X')

    for card in job_cards:
        announcement_name = card.find('span', class_='title-u2qk9xX9Ie').get_text(strip=True) if card.find('span', class_='title-u2qk9xX9Ie') else ""
        link = card.find('a')['href'] if card.find('a') else ""
        hd_dept = ""
        hd_loc = ""
        hd_job_num = ""
        hd_job_category = ""

        info_div = card.find('div', class_='info-tPG_0QGbhl')
        if info_div:
            details = info_div.get_text(separator='|').split('|')
            if len(details) >= 3:
                hd_dept = details[0].strip()
                hd_job_category = details[1].strip()
                hd_job_num = ""
                hd_loc = details[-1].strip()

        job_list.append({
            "announcement_name": announcement_name,
            "publish_time": "",  # Assuming publish_time is not available in the provided HTML
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": ""
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
