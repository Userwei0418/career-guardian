
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_listings = []

    for card in soup.find_all('div', class_='container-aOp138AX_X'):
        announcement_name = card.find('span', class_='title-u2qk9xX9Ie').get_text(strip=True) if card.find('span', class_='title-u2qk9xX9Ie') else ""
        link = card.find('a')['href'] if card.find('a') else ""
        hd_dept = card.find('div', class_='sd-Ellipsis-hiddenContent-1Skwh').get_text(strip=True) if card.find('div', class_='sd-Ellipsis-hiddenContent-1Skwh') else ""
        hd_job_category = card.find_all('div', class_='sd-Ellipsis-hiddenContent-1Skwh')[1].get_text(strip=True) if len(card.find_all('div', class_='sd-Ellipsis-hiddenContent-1Skwh')) > 1 else ""
        hd_loc = card.find_all('div', class_='sd-Ellipsis-hiddenContent-1Skwh')[2].get_text(strip=True) if len(card.find_all('div', class_='sd-Ellipsis-hiddenContent-1Skwh')) > 2 else ""
        hd_job_num = ""  # Assuming this field is not present in the provided HTML
        publish_time = ""  # Assuming this field is not present in the provided HTML
        if "实习" in announcement_name or "Intern" in announcement_name:
            hd_hopeworktype = "实习"
        else:
            hd_hopeworktype = ""

        job_listings.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category,
            "hd_hopeworktype":hd_hopeworktype
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_listings, f, ensure_ascii=False, indent=4)
