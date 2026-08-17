
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    job_cards = soup.find_all('div', class_='container-aOp138AX_X')

    for card in job_cards:
        announcement_name = card.find('span', class_='title-u2qk9xX9Ie').text.strip()
        publish_time = card.find('span', class_='published-at-PQ5IBWmbJV').text.replace('发布于 ', '').strip()
        link = card.find('a')['href']

        dept_loc = card.find('div', class_='sd-Spacing-spacing-inline-3icHv').find_all('div', class_='sd-foundation-body-secondary-1Z7H-')
        hd_dept = dept_loc[0].text.strip() if len(dept_loc) > 0 else ''
        hd_loc = dept_loc[1].text.strip() if len(dept_loc) > 1 else ''

        hd_job_num = ''  # Placeholder as the job number is not provided in the HTML
        hd_job_category = ''  # Placeholder as the job category is not provided in the HTML

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
