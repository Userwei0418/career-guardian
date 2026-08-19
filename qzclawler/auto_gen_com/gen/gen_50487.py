
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for card in soup.find_all('div', class_='container-aOp138AX_X'):
        announcement_name = card.find('span', class_='title-u2qk9xX9Ie').get_text(strip=True) if card.find('span', class_='title-u2qk9xX9Ie') else ""
        publish_time = ""  # Assuming there's no publish time in the provided HTML
        link = card.find('a')['href'] if card.find('a') else ""
        hd_dept = ""
        hd_loc = card.find_all('div', class_='no-adaptive-tooltip')[1].get_text(strip=True) if len(card.find_all('div', class_='sd-foundation-body-secondary-1Z7H-')) > 1 else ""
        hd_job_num = ""  # Assuming there's no job number in the provided HTML
        hd_job_category = card.find('div', class_='no-adaptive-tooltip').get_text(strip=True) if card.find('div', class_='sd-foundation-body-secondary-1Z7H-') else ""   # Assuming there's no job category in the provided HTML
        if hd_loc == "":
            hd_loc = "其他"
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
