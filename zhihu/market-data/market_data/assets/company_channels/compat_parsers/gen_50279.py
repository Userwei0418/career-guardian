
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    job_cards = soup.find_all('div', class_='container-aOp138AX_X')

    for card in job_cards:
        link = card.find('a', class_='link-txmgVOCVz9')['href']
        title = card.find('span', class_='title-u2qk9xX9Ie').text.strip()
        publish_time = card.find('span', class_='published-at-PQ5IBWmbJV').text.replace('发布于 ', '').strip()
        hd_dept = card.find('div', class_='sd-Ellipsis-hiddenContent-1Skwh').text.strip()

        job_info = {
            "announcement_name": title,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": "",  # Placeholder as location is not provided in the HTML
            "hd_job_num": "",  # Placeholder as job number is not provided in the HTML
            "hd_job_category": ""  # Placeholder as job category is not provided in the HTML
        }

        job_list.append(job_info)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
