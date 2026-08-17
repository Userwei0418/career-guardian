
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for card in soup.find_all('div', class_='container-aOp138AX_X'):
        announcement_name = card.find('span', class_='title-u2qk9xX9Ie').text.strip()
        publish_time = card.find('span', class_='published-at-PQ5IBWmbJV').text.replace('发布于 ', '').strip()
        link = card.find('a')['href']
        hd_dept = card.find_all('div', class_='sd-foundation-body-secondary-1Z7H-')[0].text.strip()
        hd_loc = card.find_all('div', class_='sd-foundation-body-secondary-1Z7H-')[-1].text.strip()
        hd_job_num = ""  # Assuming the job number is not provided in the HTML
        hd_job_category = card.find_all('div', class_='sd-foundation-body-secondary-1Z7H-')[1].text.strip()

        job_list.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": "",
            "hd_loc": "",
            "hd_job_num": hd_job_num,
            "hd_job_category": ""
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
