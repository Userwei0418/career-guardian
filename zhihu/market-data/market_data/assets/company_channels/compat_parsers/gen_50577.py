
import json
from bs4 import BeautifulSoup

def extract_table_from_html(html_context, temp_file):
    soup = BeautifulSoup(html_context, 'html.parser')
    job_list = []

    job_cards = soup.find_all('div', class_='container-aOp138AX_X')

    for card in job_cards:
        announcement_name = card.find('span', class_='title-u2qk9xX9Ie').get_text(strip=True) if card.find('span', class_='title-u2qk9xX9Ie') else ""
        publish_time = card.find('span', class_='published-at-PQ5IBWmbJV').get_text(strip=True) if card.find('span', class_='published-at-PQ5IBWmbJV') else ""
        link = card.find('a')['href'] if card.find('a') else ""
        hd_dept = ""  # No specific field for department in the provided HTML
        hd_loc = ""  # No specific field for location in the provided HTML
        hd_job_num = ""  # No specific field for job number in the provided HTML
        hd_job_category = ""  # No specific field for job category in the provided HTML

        # Extracting job type and location from the card
        job_info = card.find('div', class_='w-full-mRUtzMQLHs')
        if job_info:
            job_details = job_info.find_all('div', class_='no-adaptive-tooltip')
            if len(job_details) >= 2:
                hd_loc = job_details[2].get_text(strip=True) if job_details[2] else ""
                hd_job_category = job_details[1].get_text(strip=True) if job_details[1] else ""

        job_list.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        })

    with open(temp_file, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
