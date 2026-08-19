
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for card in soup.find_all('div', class_='container-aOp138AX_X'):
        announcement_name = card.find('span', class_='title-u2qk9xX9Ie').text.strip()
        publish_time = card.find('span', class_='published-at-PQ5IBWmbJV').text.replace('发布于 ', '').strip()
        link = card.find('a')['href']
        details = card.find('div', class_='info-tPG_0QGbhl').find_all('div', class_='sd-foundation-body-secondary-1Z7H-')

        hd_dept = details[0].text.strip() if len(details) > 0 else ''
        hd_loc = details[1].text.strip() if len(details) > 1 else ''
        hd_job_num = details[2].text.strip() if len(details) > 2 else ''
        hd_job_category = details[3].text.strip() if len(details) > 3 else ''

        job_list.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": "",
            "hd_loc": hd_job_category,
            "hd_job_num": "",
            "hd_job_category": hd_loc
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
