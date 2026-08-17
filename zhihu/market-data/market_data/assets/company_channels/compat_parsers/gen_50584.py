
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    job_cards = soup.find_all('div', class_='container-aOp138AX_X large-yh1BjPzxqE list-oR2doUijv4')

    for card in job_cards:
        announcement_name = card.find('span', class_='title-u2qk9xX9Ie target-color-container').get_text(strip=True) if card.find('span', class_='title-u2qk9xX9Ie target-color-container') else ""
        publish_time = card.find('span', class_='published-at-PQ5IBWmbJV').get_text(strip=True).replace("发布于 ", "") if card.find('span', class_='published-at-PQ5IBWmbJV') else ""
        link = card.find('a')['href'] if card.find('a') else ""
        hd_dept = card.find('div', class_='sd-Ellipsis-hiddenContent-1Skwh').get_text(strip=True) if card.find('div', class_='sd-Ellipsis-hiddenContent-1Skwh') else ""
        hd_loc = ""  # Location is not provided in the HTML structure
        hd_job_num = ""  # Job number is not provided in the HTML structure
        hd_job_category =  ""

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
