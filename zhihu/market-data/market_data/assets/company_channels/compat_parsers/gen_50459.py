
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    job_cards = soup.find_all('div', class_='container-aOp138AX_X')

    for card in job_cards:
        announcement_name = card.find('span', class_='title-u2qk9xX9Ie').get_text(strip=True) if card.find('span', class_='title-u2qk9xX9Ie') else ""
        publish_time = card.find('span', class_='published-at-PQ5IBWmbJV').get_text(strip=True).replace("发布于 ", "") if card.find('span', class_='published-at-PQ5IBWmbJV') else ""
        link = card.find('a')['href'] if card.find('a') else ""
        hd_dept = ""  # No specific field for department in the provided HTML
        hd_loc = ""
        hd_job_num = ""  # No specific field for job number in the provided HTML
        hd_job_category = ""

        info_divs = card.find_all('div', class_='no-adaptive-tooltip')
        if len(info_divs) >= 3:
            hd_job_category = info_divs[1].get_text(strip=True) if info_divs[1] else ""
            hd_loc = info_divs[2].get_text(strip=True) if info_divs[2] else ""
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
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category,
            "hd_hoepworktype": hd_hopeworktype
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
